# The home page film in 9:16 (FV8)

2026-11-22. The founder asked for the home page film (`fabric_backend/static/media/krusgraph-overview-web-4x5.mp4`,
45.3 s, narration AI-generated) on TikTok too; Instagram has had it since 19 November. TikTok wants 9:16, so the 4:5
film is placed unchanged on a 1080x1920 frame in its own background colour (#F4F4F4), and the site's captions
(`krusgraph-overview.en.vtt`, unchanged words) are burned in above it, clear of TikTok's buttons. Nothing else changed.

```bash
ffmpeg -i fabric_backend/static/media/krusgraph-overview-web-4x5.mp4 -filter_complex "[0:v]pad=1080:1920:0:330:color=0xF4F4F4,ass=social/films/2026-11-22-overview-9x16/caps.ass[v]" -map "[v]" -map 0:a -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart krusgraph-overview-9x16.mp4
```

`caps.ass` is the VTT's 15 cues as ASS (Inter Bold 52 px, dark on the film's background, top centre). sha256 of the film:
`c123c2e3e0088a6a7f77e16314d57b030242a8d3f02599a37da2e84e8446098c`.
