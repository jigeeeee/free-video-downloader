// Background: returns cookie arrays instead of keyed objects.

const DOMAINS = [".bilibili.com", ".douyin.com", ".youtube.com", ".tiktok.com"];

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action !== "get_cookies") return false;

  const allCookies = [];
  let pending = DOMAINS.length;

  DOMAINS.forEach((domain) => {
    chrome.cookies.getAll({ domain }, (cookies) => {
      cookies.forEach((c) => {
        allCookies.push({
          domain: c.domain,
          name: c.name,
          value: c.value,
          path: c.path || "/",
          secure: c.secure,
          expirationDate: c.expirationDate,
        });
      });
      pending -= 1;
      if (pending === 0) {
        console.log("[CookieSync BG] Found", allCookies.length, "cookies");
        sendResponse({ success: true, cookies: allCookies });
      }
    });
  });

  return true;
});
