import json
import urllib.parse
import time
from typing import Dict, List, Optional, Any
from hashlib import md5

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 使用 socks5h:// 以防止海外服务器 DNS 泄漏
RESOLVE_PROXY = ""

def get_safe_proxy(use_proxy: bool) -> Optional[Dict[str, str]]:
    if use_proxy and RESOLVE_PROXY:
        return {"http": RESOLVE_PROXY, "https": RESOLVE_PROXY}
    return None

class APIConstants:
    AES_KEY = b"e82ckenh8dichen8"
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154'
    REFERER = 'https://music.163.com/'
    
    LYRIC_API = "https://interface3.music.163.com/api/song/lyric"
    SEARCH_API = 'https://music.163.com/api/cloudsearch/pc'
    
    DEFAULT_COOKIES = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!"
    }

class CryptoUtils:
    
    @staticmethod
    def hex_digest(data: bytes) -> str:
        return "".join([hex(d)[2:].zfill(2) for d in data])
    
    @staticmethod
    def hash_digest(text: str) -> bytes:
        return md5(text.encode("utf-8")).digest()
    
    @staticmethod
    def hash_hex_digest(text: str) -> str:
        return CryptoUtils.hex_digest(CryptoUtils.hash_digest(text))
    
    @staticmethod
    def encrypt_params(url: str, payload: Dict[str, Any]) -> str:
        url_path = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
        digest = CryptoUtils.hash_hex_digest(f"nobody{url_path}use{json.dumps(payload)}md5forencrypt")
        params = f"{url_path}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
        
        padder = padding.PKCS7(algorithms.AES(APIConstants.AES_KEY).block_size).padder()
        padded_data = padder.update(params.encode()) + padder.finalize()
        cipher = Cipher(algorithms.AES(APIConstants.AES_KEY), modes.ECB())
        encryptor = cipher.encryptor()
        enc = encryptor.update(padded_data) + encryptor.finalize()
        
        return CryptoUtils.hex_digest(enc)

class APIException(Exception):
    pass

class HTTPClient:    
    _session = requests.Session()
    
    @staticmethod
    def _reset_session():
        try:
            HTTPClient._session.close()
        except:
            pass
        HTTPClient._session = requests.Session()

    @staticmethod
    def post_request(url: str, params: str, cookies: Dict[str, str], use_proxy: bool = False, max_retries: int = 5) -> str:
        headers = {
            'User-Agent': APIConstants.USER_AGENT,
            'Referer': APIConstants.REFERER,
        }
        request_cookies = APIConstants.DEFAULT_COOKIES.copy()
        request_cookies.update(cookies)
        
        proxies = get_safe_proxy(use_proxy)
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"⚠️ [网络波动-POST] 第 {attempt+1} 次重试...")
                    
                response = HTTPClient._session.post(
                    url, headers=headers, cookies=request_cookies, 
                    data={"params": params}, timeout=(10, 30), proxies=proxies
                )
                response.raise_for_status()
                return response.text
                
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code < 500:
                    raise
            except requests.exceptions.RequestException as e:
                print(f"⚠️ 网络异常: {e}")
            
            HTTPClient._reset_session()
            sleep_time = min(1.5 * (2 ** attempt), 10)
            time.sleep(sleep_time)
            
        raise APIException(f"HTTP请求失败(已重试{max_retries}次)")

class NeteaseAPI:    
    def __init__(self):
        self.http_client = HTTPClient()
        self.crypto_utils = CryptoUtils()

    def get_lyric(self, song_id: int, cookies: Dict[str, str], use_proxy: bool = False) -> Dict[str, Any]:
        try:
            data = {
                'id': song_id, 
                'cp': 'false', 
                'tv': '0', 
                'lv': '0', 
                'rv': '0', 
                'kv': '0', 
                'yv': '0', 
                'ytv': '0', 
                'yrv': '0'
            }
            headers = {'User-Agent': APIConstants.USER_AGENT, 'Referer': APIConstants.REFERER}
            
            response = HTTPClient._session.post(APIConstants.LYRIC_API, data=data, 
                                   headers=headers, cookies=cookies, timeout=30, proxies=get_safe_proxy(use_proxy))
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') != 200:
                raise APIException(f"获取歌词失败: {result.get('message', '未知错误')}")
            
            return result
        except requests.RequestException as e:
            raise APIException(f"获取歌词请求失败: {e}")
        except json.JSONDecodeError as e:
            raise APIException(f"解析歌词响应失败: {e}")
    
    def get_song_comments(self, song_id: int, limit: int = 20, offset: int = 0, use_proxy: bool = False) -> Dict[str, Any]:
        try:
            payload = {
                'rid': f'R_SO_4_{song_id}',
                'limit': limit,
                'offset': offset,
                'beforeTime': 0
            }
            url = f'https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}'
            
            params = self.crypto_utils.encrypt_params(url, payload)
            response_text = self.http_client.post_request(url, params, {}, use_proxy=use_proxy)
            
            result = json.loads(response_text)
            if result.get('code') != 200:
                raise APIException("获取评论失败")
            return result
        except Exception as e:
            raise APIException(f"评论请求错误: {e}")
    
    def search_music(self, keywords: str, cookies: Dict[str, str], limit: int = 10, search_type: int = 1, use_proxy: bool = False) -> List[Dict[str, Any]]:
        try:
            data = {'s': keywords, 'type': search_type, 'limit': limit}
            headers = {'User-Agent': APIConstants.USER_AGENT, 'Referer': APIConstants.REFERER}
            
            response = HTTPClient._session.post(APIConstants.SEARCH_API, data=data, 
                                   headers=headers, cookies=cookies, timeout=30, proxies=get_safe_proxy(use_proxy))
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') != 200:
                raise APIException(f"搜索失败: {result.get('message', '未知错误')}")
            
            results = []
            if search_type == 1: # 歌曲
                for item in result.get('result', {}).get('songs', []):
                    results.append({
                        'id': item['id'],
                        'name': item['name'],
                        'artists': '/'.join(artist['name'] for artist in item.get('ar', [])),
                        'album': item.get('al', {}).get('name', ''),
                        'al': item.get('al', {}), 
                        'picUrl': item.get('al', {}).get('picUrl', '')
                    })
            elif search_type == 10: # 专辑
                for item in result.get('result', {}).get('albums', []):
                    results.append({
                        'id': item['id'],
                        'name': item['name'],
                        'artists': item.get('artist', {}).get('name', ''),
                        'picUrl': item.get('picUrl', '')
                    })
            elif search_type == 100: # 歌手
                for item in result.get('result', {}).get('artists', []):
                    results.append({
                        'id': item['id'],
                        'name': item['name'],
                        'picUrl': item.get('picUrl', '') or item.get('img1v1Url', '')
                    })
            
            return results
        except requests.RequestException as e:
            raise APIException(f"搜索请求失败: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            raise APIException(f"解析搜索响应失败: {e}")

if __name__ == "__main__":
    print("网易云 API 就绪")