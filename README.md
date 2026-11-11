# video-download-pipeline

用 yt-dlp 把视频按 **平台 / 播放列表 / 作者** 归档的一套本地配置和脚本。

仓库只保存工具链。视频、音频、字幕、讲义 PDF、压缩包和真实 cookie 都不入库。

## 解决什么问题

- YouTube、Bilibili、抖音、小红书、微博、TikTok 共用一套输出目录规则。
- 抖音、小红书、B 站需要登录态。脚本从专用 Chrome profile 导出 Netscape cookies，yt-dlp 按目标域名自动取用。
- 同分辨率优先选高码率，避免 B 站默认挑到码率偏低的 AV1。
- 未完成的分片放 `.tmp`，下完再移动到正式目录，成品目录里不会出现半截文件。

## 目录结构

```text
video-download-pipeline/
├── config/
│   └── yt-dlp.conf.template      # yt-dlp 全局配置模板
├── scripts/
│   ├── cookie-export.py          # 从 Chrome profile 导出 cookie
│   ├── install-config.ps1        # 生成实际配置并创建目录
│   └── open-chrome-profile.cmd   # 打开专用 Chrome profile
├── .cookies/
│   ├── _template.txt             # Netscape cookie 格式示例
│   └── README.md
├── bilibili/  douyin/  tiktok/  weibo/  xiaohongshu/  youtube/
├── .gitignore
└── requirements.txt
```

下载后的实际结构：

```text
<下载根目录>/
└── <平台>/
    └── <播放列表或 No Playlist>/
        └── <作者>/
            └── <标题> [<视频ID>].mp4
```

## 依赖

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- ffmpeg（合并音视频、转封装）
- Node.js（YouTube 的 JS challenge 需要）
- Python 3.10+ 和 `cryptography`（只用于导出 cookie）

Windows 下用 scoop 安装：

```powershell
scoop install yt-dlp ffmpeg nodejs
pip install -r requirements.txt
```

## 安装配置

在仓库根目录执行：

```powershell
.\scripts\install-config.ps1 -Root "D:\视频下载"
```

脚本会做四件事：

1. 把 `config/yt-dlp.conf.template` 里的 `{{ROOT}}` 替换成实际下载根目录。
2. 写入 `C:\scoop\persist\yt-dlp\yt-dlp.conf`；没有 scoop 时写到 `%APPDATA%\yt-dlp\config`。
3. 原配置存在时先备份为 `yt-dlp.conf.bak-<时间>`。
4. 创建 `.cookies`、`.tmp` 和各平台目录。

## 导出 cookie

先打开专用 Chrome profile，登录需要登录的站点，然后**完全关闭这个 Chrome 窗口**：

```powershell
.\scripts\open-chrome-profile.cmd
```

再导出：

```powershell
python .\scripts\cookie-export.py
```

默认读取 `%LOCALAPPDATA%\tools\chrome-ytdlp\Default`，输出到仓库的 `.cookies`：

- `<站点>.txt`：Netscape 格式，给 yt-dlp 用。
- `<站点>.str`：单行 cookie 字符串，给其它下载器用。
- `all.txt`：所有站点合并，yt-dlp 全局配置引用这一份。

yt-dlp 只会发送与目标域名匹配的 cookie，不会把 B 站 cookie 发给抖音。

自定义路径：

```powershell
python .\scripts\cookie-export.py --profile-dir "D:\chrome-profile" --out "D:\视频下载\.cookies"
```

`--profile-dir` 可以给 user-data-dir，也可以直接给 `Default` 目录，脚本会自动识别。

## 下载

```powershell
# 单个视频
yt-dlp "https://www.youtube.com/watch?v=oS9aPzUNG-s"

# 播放列表，带英文字幕
yt-dlp --write-subs --sub-langs "en.*" --convert-subs srt "https://www.youtube.com/playlist?list=..."

# B 站
yt-dlp "https://www.bilibili.com/video/BV..."

# 只检查解析，不下载
yt-dlp --simulate "https://www.douyin.com/video/..."
```

输出路径、画质、cookie 都由全局配置决定，命令行不用重复写。

## 配置说明

`config/yt-dlp.conf.template` 里几个关键项：

| 配置 | 作用 |
| --- | --- |
| `--js-runtimes node` | 让 yt-dlp 用 Node 解 YouTube 的 JS challenge，否则部分格式会缺失 |
| `--cookies "{{ROOT}}/.cookies/all.txt"` | 统一登录态入口 |
| `-P "{{ROOT}}"` | 成品根目录 |
| `-o "%(extractor)s/%(playlist\|No Playlist)s/%(uploader\|unknown)s/%(title)s [%(id)s].%(ext)s"` | 平台 / 播放列表 / 作者 / 标题 |
| `-P "temp:{{ROOT}}/.tmp"` | 未完成分片目录 |
| `-S "res,br"` | 先按分辨率、再按码率排序 |
| `-f "bv*+ba/b"` | 优先最佳视频 + 最佳音频，失败时退回单文件 |
| `--merge-output-format mp4` | 合并后统一为 mp4 |

需要默认下载字幕时，取消模板末尾三行的注释：

```conf
--write-subs
--sub-langs "en.*,zh.*"
--convert-subs srt
```

## 常见问题

**导出 0 条 cookie**

Chrome 没登录，或者 profile 路径不对。先确认 `chrome-ytdlp\Default\Network\Cookies` 存在，并且 Chrome 已关闭。

**抖音、小红书解析失败**

先看 `.cookies\all.txt` 里有没有对应站点的 cookie。Chrome 130+ 的 app-bound 加密（`v20`）无法用 DPAPI 解，脚本会跳过并打印失败项。

**YouTube 提示 Sign in to confirm you're not a bot**

换节点后重新登录并导出 cookie。机房 IP 被风控时，cookie 也救不了。

**B 站只有 360p**

没登录，或者 ffmpeg 不在 PATH。先确认 `yt-dlp --simulate` 能列出 1080p 格式。

**文件名过长**

在配置里加 `--windows-filenames --trim-filenames 120`。

**cookie 过期**

重开专用 Chrome profile 登录一次，关闭窗口，重新运行 `cookie-export.py`。

## 说明

仓库的 `.gitignore` 会排除所有媒体、PDF、压缩包、日志和 `.cookies` 下的真实凭据。只有脚本、模板和文档会进入 Git。

仅用于下载你有权访问的内容，遵守各平台的服务条款。
