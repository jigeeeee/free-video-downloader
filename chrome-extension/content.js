// Content script: asks background for cookies, posts to the local backend.

const BACKEND_CANDIDATES = [
  "http://127.0.0.1:8002",
  "http://localhost:8002",
  "http://127.0.0.1:8001",
  "http://localhost:8001",
  "http://127.0.0.1:8003",
  "http://localhost:8003",
  "http://127.0.0.1:8000",
  "http://localhost:8000",
];

async function postCookies(cookies) {
  let lastError = null;
  for (const baseUrl of BACKEND_CANDIDATES) {
    try {
      const response = await fetch(`${baseUrl}/api/cookies/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookies }),
      });
      if (!response.ok) {
        lastError = new Error(`${baseUrl} returned ${response.status}`);
        continue;
      }
      const data = await response.json();
      console.log("[CookieSync] Synced cookies to", baseUrl, data);
      return data;
    } catch (error) {
      lastError = error;
    }
  }
  if (lastError) {
    console.warn("[CookieSync] API error:", lastError);
  }
  return null;
}

function syncCookies() {
  chrome.runtime.sendMessage({ action: "get_cookies" }, (response) => {
    if (chrome.runtime.lastError) {
      console.log("[CookieSync] Extension error:", chrome.runtime.lastError.message);
      return;
    }
    if (!response || !response.success) return;

    const cookies = response.cookies || [];
    if (!Array.isArray(cookies) || cookies.length === 0) return;

    postCookies(cookies);
  });
}

syncCookies();
setInterval(syncCookies, 30 * 60 * 1000);
