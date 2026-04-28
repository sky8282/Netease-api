import re
import httpx
import uvicorn

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.concurrency import run_in_threadpool
from api import NeteaseAPI, APIConstants

app = FastAPI(title="网易云 API", description="歌手头像，双语歌词，曲目评论，专辑封面 API")
netease_api = NeteaseAPI()
http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=100))

def get_global_cookies():
    return {}

def merge_translated_lyrics(lrc: str, tlyric: str) -> str:
    if not tlyric or not lrc:
        return lrc
    
    pattern = re.compile(r'\[(\d{2}:\d{2})(?:\.\d{2,3})?\](.*)')
    t_map = {}
    
    for line in tlyric.split('\n'):
        match = pattern.match(line)
        if match:
            time_key, text = match.groups()
            if text.strip():
                t_map[time_key] = text.strip()
                
    merged = []
    for line in lrc.split('\n'):
        match = pattern.match(line)
        if match:
            time_key, text = match.groups()
            text = text.strip()
            original_time_tag = re.search(r'\[(.*?)\]', line).group(1)
            merged.append(f"[{original_time_tag}]{text}")
            if time_key in t_map and t_map[time_key]:
                merged.append(f"[{original_time_tag}]{t_map[time_key]}")
        else:
            merged.append(line)
    return '\n'.join(merged)

# ==========================================
# 1. 曲目评论 API
# ==========================================
@app.api_route("/api/comment/list", methods=["GET", "POST"])
async def arrow_music_comments_api(request: Request):
    data = {}
    if request.method == "POST":
        try: data = await request.json()
        except: pass
    if not data:
        data = dict(request.query_params)

    song_name = data.get('song_name', '').strip()
    singer_name = data.get('singer_name', '').strip()
    start = int(data.get('start', 0))
    
    print("="*50)
    print(f"🐛 [DEBUG - 曲目评论 API] 收到客户端请求")
    print(f"   ├─ 歌曲: {song_name} - {singer_name}")
    print(f"   └─ 客户端请求的 Start(Offset): {start}")

    empty_response = {"code": 200, "msg": "获取成功", "body": []}
    if not song_name: 
        print("   ❌ 歌曲名为空，直接返回空数组")
        return JSONResponse(empty_response)
        
    try:
        cookies = get_global_cookies()
        primary_singer = re.split(r'[/,&]', singer_name)[0].strip() if singer_name else ""
        
        search_queries = []
        if singer_name: search_queries.append(f"{song_name} {singer_name}")
        if primary_singer and primary_singer != singer_name: search_queries.append(f"{song_name} {primary_singer}")
        search_queries.append(song_name)
        
        search_results = []
        print(f"   🔍 开始搜索歌曲 ID...")
        for query in search_queries:
            try:
                search_results = await run_in_threadpool(netease_api.search_music, query, cookies, limit=1, search_type=1)
                if search_results: 
                    print(f"   ✅ 搜索成功: 关键词 [{query}]")
                    break
            except: continue
            
        if not search_results: 
            print("   ❌ 未搜索到对应歌曲，返回空数组")
            return JSONResponse(empty_response)
            
        song_id = search_results[0]['id']
        print(f"   🎯 获取到网易云歌曲 ID: {song_id}")
        
        target_total = 100
        per_page = 20
        formatted_body = []
        seen_ids = set() 
        last_time = 0 
        
        print(f"   🔄 开始直连底层 API 聚合抓取，目标: {target_total} 条")
        
        headers = {'User-Agent': APIConstants.USER_AGENT, 'Referer': APIConstants.REFERER}
        
        import asyncio
        for current_offset in range(start, start + target_total, per_page):
            page_num = (current_offset - start) // per_page + 1
            print(f"      ▶️ [第 {page_num} 页] 裸连请求 limit={per_page}, offset={current_offset} (last_time={last_time})...")
            
            try:
                url = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?limit={per_page}&offset={current_offset}"
                if last_time > 0:
                    url += f"&before={last_time}"
                    
                res_obj = await http_client.get(url, headers=headers, cookies=cookies)
                result = res_obj.json()
                
                if result.get("code") != 200:
                    print(f"      ❌ [第 {page_num} 页] 接口返回非 200: {result.get('code')}")
                    break
            except Exception as api_e:
                print(f"      ❌ [第 {page_num} 页] 直连请求报错: {api_e}")
                break
            
            hot_count = len(result.get('hotComments', [])) if current_offset == start else 0
            comments = result.get('comments', [])
            norm_count = len(comments)
            print(f"      ✅ [第 {page_num} 页] 拿到原始数据: 热评 {hot_count} 条, 普通 {norm_count} 条")
            
            if current_offset == start and result.get('hotComments'):
                for c in result['hotComments']:
                    cid = str(c.get('commentId', ''))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        create_time_sec = int(c.get('time', 0) / 1000)
                        formatted_body.append({
                            "nick": c.get('user', {}).get('nickname', '匿名'),
                            "avatarurl": c.get('user', {}).get('avatarUrl', ''),
                            "content": f"🔥 [热评] {c.get('content', '')}",
                            "praiseNum": c.get('likedCount', 0),
                            "createTime": create_time_sec,
                            "commentId": cid
                        })
            
            added_this_round = 0
            for c in comments:
                cid = str(c.get('commentId', ''))
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    added_this_round += 1
                    create_time_sec = int(c.get('time', 0) / 1000)
                    formatted_body.append({
                        "nick": c.get('user', {}).get('nickname', '匿名'),
                        "avatarurl": c.get('user', {}).get('avatarUrl', ''),
                        "content": c.get('content', ''),
                        "praiseNum": c.get('likedCount', 0),
                        "createTime": create_time_sec,
                        "commentId": cid
                    })
            
            print(f"      📊 本页成功去重录入: {added_this_round} 条。当前总池: {len(formatted_body)} 条")
            
            if comments:
                last_time = comments[-1].get('time', 0)
            
            if added_this_round == 0 and norm_count > 0:
                print(f"      ⚠️ [第 {page_num} 页] 网易云死锁：重复数据。无有效 Cookie 状态下强行翻页失败，终止。")
                break
                
            if not comments:
                print(f"      ⚠️ [第 {page_num} 页] 没有普通评论了，提前终止")
                break
                    
            await asyncio.sleep(0.3)

        print(f"   🎉 聚合完成！最终发给客户端 {len(formatted_body)} 条评论")
        print("="*50)
        return JSONResponse({"code": 200, "msg": "获取成功", "body": formatted_body})
        
    except Exception as e:
        print(f"❌ 评论接口全局异常: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(empty_response)

@app.api_route("/api/song/comments", methods=["GET", "POST"])
async def get_raw_song_comments_api(request: Request, id: str = Query(...), limit: int = Query(100), offset: int = Query(0)):
    try:
        url = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{id}?limit={limit}&offset={offset}"
        headers = {'User-Agent': APIConstants.USER_AGENT, 'Referer': APIConstants.REFERER}
        res_obj = await http_client.get(url, headers=headers, cookies=get_global_cookies())
        return JSONResponse(res_obj.json())
    except Exception as e:
        return JSONResponse({"code": 500, "msg": str(e)})

# ==========================================
# 2. 歌手头像 API
# ==========================================
@app.api_route("/api/artist/avatar", methods=["GET"])
async def api_get_artist_avatar(request: Request, id: str = Query(None), name: str = Query(None)):
    fallback_img = "https://p1.music.126.net/6y-UleORITEDbvrOLV0Q8A==/5639395138885805.jpg?param=300y300"
    try:
        cookies = get_global_cookies()
        headers = {'User-Agent': APIConstants.USER_AGENT, 'Referer': APIConstants.REFERER}
        real_id = None
        
        if id:
            real_id = re.sub(r'\D', '', id)
        elif name:
            search_res = await run_in_threadpool(netease_api.search_music, name, cookies, limit=1, search_type=100)
            if search_res:
                real_id = str(search_res[0].get('id'))
                pic_url = search_res[0].get('picUrl') or search_res[0].get('img1v1Url')
                if pic_url:
                    return RedirectResponse(url=f"{pic_url.replace('http://', 'https://')}?param=1200y1200")

        if real_id:
            res_obj = await http_client.get(f'https://music.163.com/api/v1/artist/{real_id}', headers=headers, cookies=cookies)
            res = res_obj.json()
            pic_url = res.get("artist", {}).get("picUrl") or res.get("artist", {}).get("img1v1Url")
            
            if pic_url and pic_url != "None":
                return RedirectResponse(url=f"{pic_url.replace('http://', 'https://')}?param=300y300")
                
        return RedirectResponse(url=fallback_img)
    except Exception as e:
        print(f"获取歌手头像异常: {e}")
        return RedirectResponse(url=fallback_img)

# ==========================================
# 3. 双语歌词 API
# ==========================================
@app.api_route("/api/lyric", methods=["GET", "POST"])
async def api_get_bilingual_lyric(request: Request):
    try:
        data = {}
        if request.method == "POST":
            try: data = await request.json()
            except: data = dict(await request.form())
        if not data:
            data = dict(request.query_params)

        song_id = data.get("id", "")
        title = data.get("title", data.get("name", "")).strip()
        artist = data.get("artist", "").strip()
        album = data.get("album", "").strip()
        
        cookies = get_global_cookies()
        real_id = None
        
        if song_id:
            real_id = re.sub(r'\D', '', str(song_id))
        elif title:
            search_query = f"{title} {artist} {album}".strip()
            search_res = await run_in_threadpool(netease_api.search_music, search_query, cookies, limit=5, search_type=1)
            if search_res:
                best_match = search_res[0]
                if artist:
                    from difflib import SequenceMatcher
                    best_score = 0
                    target_artist = artist.lower()
                    for song in search_res:
                        song_artists = song.get('artists', '').lower()
                        score = SequenceMatcher(None, target_artist, song_artists).ratio()
                        if target_artist in song_artists: score += 0.5
                        if score > best_score:
                            best_score = score
                            best_match = song
                real_id = str(best_match['id'])

        if not real_id:
            return JSONResponse({"code": 404, "msg": "未提供有效参数或未能搜索到匹配歌曲", "lrc": ""})
        
        lyric_data = await run_in_threadpool(netease_api.get_lyric, int(real_id), cookies)
        lrc_text = lyric_data.get("lrc", {}).get("lyric", "")
        tlyric_text = lyric_data.get("tlyric", {}).get("lyric", "")

        def clean_lyric(text: str) -> str:
            if not text: return ""
            text = re.sub(r'\[by:.*?\]\n?', '', text)
            text = re.sub(r'\[\d{2}:\d{2}[\.:]\d{2,3}\].*?(www\.|.net|.com).*?\n?', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\[\d{2}:\d{2}[\.:]\d{2,3}\].*?(翻译:|QQ:|微信:).*?\n?', '', text, flags=re.IGNORECASE)
            return text.strip()

        lrc_text = clean_lyric(lrc_text)
        tlyric_text = clean_lyric(tlyric_text)
        
        if not lrc_text:
            return JSONResponse({"code": 404, "msg": f"未找到歌词 (云端ID: {real_id})", "lrc": ""})
        
        final_lyric = merge_translated_lyrics(lrc_text, tlyric_text)
        
        return JSONResponse({
            "code": 200, 
            "msg": "获取成功", 
            "matched_id": real_id,
            "lrc": final_lyric,
            "raw_lrc": lrc_text,
            "tlyric": tlyric_text
        })
    except Exception as e:
        return JSONResponse({"code": 500, "msg": str(e), "lrc": ""})

# ==========================================
# 4. 专辑封面 API
# ==========================================
@app.api_route("/api/album/cover", methods=["GET"])
async def api_get_album_cover(request: Request, album: str = Query(None), artist: str = Query(None), title: str = Query(None), name: str = Query(None)):
    fallback_img = "https://p1.music.126.net/6y-UleORITEDbvrOLV0Q8A==/5639395138885805.jpg?param=300y300"
    
    try:
        search_title = title or name or ""
        if not album and search_title:
            if "-" in search_title:
                parts = search_title.split("-", 1)
                artist = parts[0].strip()
                album = parts[1].strip()
            else:
                album = search_title.strip()

        if not album:
            return RedirectResponse(url=fallback_img)

        cookies = get_global_cookies()
        search_query = f"{album} {artist or ''}".strip()
        
        search_res = await run_in_threadpool(netease_api.search_music, search_query, cookies, limit=5, search_type=10)
        
        if search_res:
            from difflib import SequenceMatcher
            
            best_match = None
            best_score = 0
            
            target_album = album.lower()
            target_artist = (artist or "").lower()
            
            for item in search_res:
                item_album = item.get('name', '').lower()
                item_artist = item.get('artists', '').lower()
                
                album_score = SequenceMatcher(None, target_album, item_album).ratio()
                
                if target_album in item_album or item_album in target_album:
                    album_score = max(album_score, 0.95)
                if album_score < 0.9:
                    continue
                    
                artist_score = 0
                if target_artist:
                    artist_score = SequenceMatcher(None, target_artist, item_artist).ratio()
                    if target_artist in item_artist or item_artist in target_artist:
                        artist_score = max(artist_score, 0.95)
                total_score = (album_score * 2) + artist_score
                
                if total_score > best_score:
                    best_score = total_score
                    best_match = item
            
            if best_match:
                pic_url = best_match.get("picUrl", "")
                if pic_url:
                    final_url = f"{pic_url.replace('http://', 'https://')}?param=1200y1200"
                    return RedirectResponse(url=final_url)
                    
        return RedirectResponse(url=fallback_img)
    except Exception as e:
        print(f"获取专辑封面异常: {e}")
        return RedirectResponse(url=fallback_img)

if __name__ == "__main__":
    print("🚀 API 服务启动中...")
    print("👉 运行在: http://0.0.0.0:8800")
    uvicorn.run(app, host="0.0.0.0", port=8800)