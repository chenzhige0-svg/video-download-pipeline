# .cookies

真实 cookie 文件（`*.txt`、`*.str`、`all.txt`）已被 `.gitignore` 排除，不要提交。

`_template.txt` 只是 Netscape 格式示例，值全是假的。

生成方式：

```powershell
python scripts\cookie-export.py
```

`all.txt` 是给 yt-dlp 全局配置用的合并文件。yt-dlp 只发送与目标域名匹配的 cookie。
