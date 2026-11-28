import { MMDLoader } from 'three-stdlib';

self.onmessage = async ({ data: url }: MessageEvent<string>) => {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`PMX HTTP ${response.status}`);
    // Use the same parser and handedness conversion as MMDLoader.loadPMX.
    const loader = new MMDLoader() as unknown as {
      _getParser(): { parsePmx(buffer: ArrayBuffer, convert: boolean): object };
    };
    self.postMessage({ model: loader._getParser().parsePmx(await response.arrayBuffer(), true) });
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : String(error) });
  }
};
