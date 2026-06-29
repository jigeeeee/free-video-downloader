// Content script — asks background for cookies, posts to backend.

function syncCookies() {
  chrome.runtime.sendMessage({ action: "get_cookies" }, (response) => {
    if (chrome.runtime.lastError) {
      console.log("[CookieSync] Extension error:", chrome.runtime.lastError.message);
      return;
    }
    if (!response || !response.success) return;
    const cookies = response.cookies;
    const count = Object.keys(cookies).length;
    if (count === 0) return;

    fetch("http://127.0.0.1:8001/api/cookies/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookies }),
    })
    .then(r => r.json())
    .then(d => console.log(`[CookieSync] Synced ${d.count} cookies`))
    .catch(e => console.warn("[CookieSync] API error:", e));
  });
}

syncCookies();
setInterval(syncCookies, 30 * 60 * 1000);
