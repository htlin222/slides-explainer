"""Default style knobs. Copied into production/<slug>/config/style.json on init.

Everything that affects pixels or timing lives here so a style tweak is a config
edit + a re-render, never a code change.
"""

DEFAULT_STYLE = {
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "vcodec": "libx264",
        "pix_fmt": "yuv420p",
        "crf": 18,
        "preset": "medium",
        "acodec": "aac",
        "abitrate": "192k",
    },
    "raster": {"dpi": 150},
    "tts": {"voice": "en-US-AndrewNeural", "rate": "+0%", "volume": "+0%"},
    # per-segment padding in seconds; clip_frames = ceil((audio_s + lead + post) * fps)
    "gaps_s": {
        "lead": 0.3,
        "post_content": 0.6,
        "post_keypoint": 0.8,
        "title_settle": 0.4,
        "end_hold": 1.2,
    },
    "caption": {
        "burn": False,              # False (default): fast, soft-mux master.srt; True: hard-burn via overlay
        "font_family": "'Helvetica Neue', 'Arial', sans-serif",
        "font_size": 46,
        "font_weight": 600,
        "color": "#ffffff",
        "band_color": "#000000",
        "band_opacity": 0.72,
        "band_pad_x": 40,
        "band_pad_y": 20,
        "band_radius": 12,
        "max_width_pct": 86,
        "y_from_bottom": 70,
        "words_per_cue": 9,
        "max_chars_per_cue": 46,
    },
    "keypoint": {
        "bg": "#ffffff",
        "title": "Key Points",
        "title_color": "#1a1a1a",
        "title_size": 60,
        "bullet_color": "#222222",
        "bullet_size": 40,
        "bullet_line_height": 1.5,
        "accent": "#c0392b",
        "font_family": "'Helvetica Neue', 'Arial', sans-serif",
        "pad_x": 120,
        "pad_top": 90,
        "max_points": 5,
    },
}
