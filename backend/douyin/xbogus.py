# Douyin X-Bogus signature generator
# Source: https://github.com/jiji262/douyin-downloader

import base64
import hashlib
import time
from typing import List, Optional, Tuple, Union

class XBogus:
    def __init__(self, user_agent: Optional[str] = None) -> None:
        self._array = [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, 10, 11, 12, 13, 14, 15
        ]
        self._character = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
        self._ua_key = b"\x00\x01\x0c"
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def _md5_str_to_array(self, md5_str: str) -> List[int]:
        if len(md5_str) > 32:
            return [ord(c) for c in md5_str]
        arr = []
        i = 0
        while i < len(md5_str):
            arr.append((self._array[ord(md5_str[i])] << 4) | self._array[ord(md5_str[i + 1])])
            i += 2
        return arr

    def _md5(self, data):
        if isinstance(data, str):
            data = self._md5_str_to_array(data)
        return hashlib.md5(bytes(data)).hexdigest()

    def _md5_encrypt(self, url_path: str):
        h = self._md5(self._md5_str_to_array(self._md5(url_path)))
        return self._md5_str_to_array(h)

    def _rc4_encrypt(self, key: bytes, data: bytes):
        s = list(range(256))
        j = 0
        encrypted = bytearray()
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) % 256
            s[i], s[j] = s[j], s[i]
        i = j = 0
        for byte in data:
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            encrypted.append(byte ^ s[(s[i] + s[j]) % 256])
        return encrypted

    def _encoding_conversion(self, a, b, c, e, d, t, f, r, n, o, i, _, x, u, s, l, v, h, p):
        payload = [a, int(i), b, _, c, x, e, u, d, s, t, l, f, v, r, h, n, p, o]
        return bytes(payload).decode("ISO-8859-1")

    def _encoding_conversion2(self, a, b, c):
        return chr(a) + chr(b) + c

    def _calculation(self, a1, a2, a3):
        x3 = ((a1 & 255) << 16) | ((a2 & 255) << 8) | (a3 & 255)
        return (
            self._character[(x3 & 16515072) >> 18]
            + self._character[(x3 & 258048) >> 12]
            + self._character[(x3 & 4032) >> 6]
            + self._character[x3 & 63]
        )

    def build(self, url: str):
        ua_md5_arr = self._md5_str_to_array(
            self._md5(
                base64.b64encode(
                    self._rc4_encrypt(self._ua_key, self._user_agent.encode("ISO-8859-1"))
                ).decode("ISO-8859-1")
            )
        )
        empty_arr = self._md5_str_to_array(self._md5(self._md5_str_to_array("d41d8cd98f00b204e9800998ecf8427e")))
        url_md5_arr = self._md5_encrypt(url)

        timer = int(time.time())
        ct = 536919696
        new_arr = [
            64, 0.00390625, 1, 12,
            url_md5_arr[14], url_md5_arr[15],
            empty_arr[14], empty_arr[15],
            ua_md5_arr[14], ua_md5_arr[15],
            timer >> 24 & 255, timer >> 16 & 255, timer >> 8 & 255, timer & 255,
            ct >> 24 & 255, ct >> 16 & 255, ct >> 8 & 255, ct & 255,
        ]
        xor = new_arr[0]
        for v in new_arr[1:]:
            xor ^= int(v) if isinstance(v, float) else v
        new_arr.append(xor)

        a3, a4 = [], []
        for i, v in enumerate(new_arr):
            if i % 2 == 0: a3.append(v)
            else: a4.append(v)

        merged = a3 + a4
        garbled = self._encoding_conversion2(
            2, 255,
            self._rc4_encrypt(
                b"\xff",
                self._encoding_conversion(*merged).encode("ISO-8859-1"),
            ).decode("ISO-8859-1"),
        )
        xb = ""
        for i in range(0, len(garbled), 3):
            xb += self._calculation(ord(garbled[i]), ord(garbled[i+1]), ord(garbled[i+2]))

        signed_url = f"{url}&X-Bogus={xb}"
        return signed_url, xb, self._user_agent
