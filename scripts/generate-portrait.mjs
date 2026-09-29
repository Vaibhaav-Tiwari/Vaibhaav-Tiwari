#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = new URL("../assets/profile-source.png", import.meta.url);
const output = new URL("../assets/art.txt", import.meta.url);
const bmpPath = join(tmpdir(), `vaibhaav-profile-${process.pid}.bmp`);

mkdirSync(new URL("../assets/", import.meta.url), { recursive: true });

// Convert the source portrait to a tiny bitmap using macOS' built-in image tool.
execFileSync("sips", [
  "--resampleHeightWidth", "74", "92",
  "-s", "format", "bmp",
  source.pathname,
  "--out", bmpPath,
], { stdio: "ignore" });

const bmp = readFileSync(bmpPath);
const pixelOffset = bmp.readUInt32LE(10);
const width = bmp.readInt32LE(18);
const rawHeight = bmp.readInt32LE(22);
const height = Math.abs(rawHeight);
const bitsPerPixel = bmp.readUInt16LE(28);
const bytesPerPixel = bitsPerPixel / 8;
const rowSize = Math.ceil((width * bitsPerPixel) / 32) * 4;
const palette = " .,:;irsXA253hMHGS#9B&@";
const lines = [];

if (![24, 32].includes(bitsPerPixel)) {
  throw new Error(`Unsupported BMP depth: ${bitsPerPixel}`);
}

for (let y = 0; y < height; y += 1) {
  let line = "";
  const sourceY = rawHeight > 0 ? height - y - 1 : y;
  for (let x = 0; x < width; x += 1) {
    const offset = pixelOffset + sourceY * rowSize + x * bytesPerPixel;
    const blue = bmp[offset];
    const green = bmp[offset + 1];
    const red = bmp[offset + 2];
    const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    const adjusted = Math.max(0, Math.min(255, (luminance - 12) * 1.16));
    const index = Math.round((adjusted / 255) * (palette.length - 1));
    line += palette[index];
  }
  lines.push(line.replace(/\s+$/, ""));
}

while (lines.length && !lines[0].trim()) lines.shift();
while (lines.length && !lines.at(-1).trim()) lines.pop();

writeFileSync(output, `${lines.join("\n")}\n`);
rmSync(bmpPath, { force: true });
console.log(`Generated ${lines.length} rows in assets/art.txt`);
