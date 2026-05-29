// Audio helpers for the live voice loop. The server speaks 16-bit mono PCM
// (base64) and accepts the same encoding for prospect audio.

export function pcm16ToAudioBuffer(ctx, b64, sampleRate) {
  const bin = atob(b64);
  const len = Math.floor(bin.length / 2);
  const buffer = ctx.createBuffer(1, len, sampleRate);
  const ch = buffer.getChannelData(0);
  for (let i = 0; i < len; i++) {
    const lo = bin.charCodeAt(i * 2);
    const hi = bin.charCodeAt(i * 2 + 1);
    let val = (hi << 8) | lo;
    if (val >= 0x8000) val -= 0x10000;
    ch[i] = val / 32768;
  }
  return buffer;
}

export function float32ToPcm16Base64(float32) {
  const out = new Uint8Array(float32.length * 2);
  for (let i = 0; i < float32.length; i++) {
    let s = Math.max(-1, Math.min(1, float32[i]));
    s = s < 0 ? s * 0x8000 : s * 0x7fff;
    out[i * 2] = s & 0xff;
    out[i * 2 + 1] = (s >> 8) & 0xff;
  }
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < out.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, out.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

export function rms(float32) {
  let sum = 0;
  for (let i = 0; i < float32.length; i++) sum += float32[i] * float32[i];
  return Math.sqrt(sum / float32.length);
}
