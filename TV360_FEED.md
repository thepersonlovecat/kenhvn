# TV360 short-link feed

The Worker supports these short routes:

`/tv3601` through `/tv36015`

Configure one of the following Worker environment variables.

## Option 1: TV360_FEED_URL

Point `TV360_FEED_URL` at an HTTPS JSON endpoint that you control. The Worker
loads the feed and caches it for 4 hours.

Example JSON:

```json
{
  "streams": {
    "tv3601": "https://example.com/channel-1/index.mpd",
    "tv3604": "https://example.com/channel-4/index.mpd?temporary=query",
    "tv3606": "https://example.com/channel-6/index.mpd"
  }
}
```

For DASH URLs, everything after `.mpd` is removed automatically. In the
example above, `/tv3604` redirects to:

```text
https://example.com/channel-4/index.mpd
```

## Option 2: TV360_STREAMS_JSON

For a small static mapping, set `TV360_STREAMS_JSON` directly to the same JSON
object instead of hosting a feed.

## Debug and refresh

Use `?json=1` to inspect the resolved URL without following the redirect:

```text
https://tivi.k-20.xyz/tv3604?json=1
```

Use `?refresh=1` to bypass the Worker's in-memory 4-hour feed cache and request
the configured feed again immediately:

```text
https://tivi.k-20.xyz/tv3604?refresh=1
```

The short route returns HTTP 302 to the configured stream URL.
