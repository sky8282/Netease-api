# Netease-api
# 🎵 Netease Subsonic Bridge (网易云元数据极速桥接 API)

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.68%2B-009688)
![License](https://img.shields.io/badge/license-MIT-green)

为 Subsonic 协议客户端（如 **DS Cloud**、**Amcfy 箭头音乐**、**Feishin** 等）打造的轻量级 API 桥接服务<br>
提供：网易云音乐的 歌手头像、专辑封面、双语歌词、曲目评论

## 🛠️ 安装与部署
### 1. 环境准备
确保你的服务器或电脑已安装 **Python 3.8** 或以上版本
### 2. 获取代码
将本仓库克隆或者下载到本地执行：
1. 安装依赖：
```bash
pip3 install -r requirements.txt --break-system-packages
```
2. 运行脚本（默认端口 8800 ）：
```bash
python3 main.py
```
## 📡 API 说明：<br>
提供以下 API 供第三方播放器调用：<br>
1. 歌手头像获取	  /api/artist/avatar	GET
示例：http://127.0.0.1:8800/api/artist/avatar?name=周杰伦<br>

2. 专辑封面	    /api/album/cover	  GET<br>
album= 专辑名称<br>
artist= 歌手名称<br>
示例：http://127.0.0.1:8800/api/album/cover?album=11月的萧邦&artist=周杰伦<br>
* 传入 "歌手名 - 专辑名"（例如 周杰伦 - 11月的萧邦）<br>
示例：http://127.0.0.1:8800/api/album/cover?album=周杰伦 - 11月的萧邦<br>

3. 歌词搜索      /api/lyric	        GET/POST<br>
* 传入 "歌手名与曲目名"<br>
title= 曲目名<br>
artist= 歌手名<br>
示例：http://127.0.0.1:8800/api/lyric?title=夜曲&artist=周杰伦<br>
* 传入 "歌手名，专辑名 与 曲目名"<br>
title= 曲目名<br>
artist= 歌手名<br>
album= 专辑名<br>
示例：http://127.0.0.1:8800/api/lyric?title=夜曲&artist=周杰伦&album=十一月的萧邦<br>

4. 单曲评论	  /api/comment/list	  GET/POST<br>
* 传入 "歌手名与曲目名"<br>
song_name= 曲目名<br>
singer_name= 歌手名<br>
示例：http://127.0.0.1:8800/api/comment/list?song_name=夜曲&singer_name=周杰伦<br>

