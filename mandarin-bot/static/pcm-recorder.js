// AudioWorklet that turns microphone audio into 16 kHz, 16-bit mono PCM —
// the input format the Gemini Live API expects. The AudioContext runs at
// the device's native rate (Firefox can't mix rates on one graph), so we
// downsample here by averaging each group of input samples.

const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 1600; // 100 ms per message

class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE;
    this.pos = 0;
    this.acc = 0;
    this.count = 0;
    this.sumSq = 0;
    this.buf = new Int16Array(CHUNK_SAMPLES);
    this.n = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.acc += channel[i];
      this.count++;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const s = Math.max(-1, Math.min(1, this.acc / this.count));
        this.acc = 0;
        this.count = 0;
        this.sumSq += s * s;
        this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.n === CHUNK_SAMPLES) {
          const rms = Math.sqrt(this.sumSq / CHUNK_SAMPLES);
          this.port.postMessage({ pcm: this.buf.buffer, rms }, [this.buf.buffer]);
          this.buf = new Int16Array(CHUNK_SAMPLES);
          this.n = 0;
          this.sumSq = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('pcm-recorder', PcmRecorder);
