#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = new URL("../assets/profile-source.png", import.meta.url);
const outputDir = new URL("../assets/", import.meta.url);
const bmpPath = join(tmpdir(), `vaibhaav-profile-${process.pid}.bmp`);

mkdirSync(outputDir, { recursive: true });

// These are intentionally easy to replace when the real details are ready.
const profile = {
  handle: "vaibhaav@github",
  sections: [
    ["currently.building", "<your current project>"],
    ["identity.role", "<your role / university>"],
    ["identity.location", "<your city, country>"],
    ["setup.daily", "<your daily machine>"],
    ["tools.ide", "<your editor / IDE>"],
    ["tools.shell", "<your terminal + shell>"],
    null,
    ["languages.programming", "<language one, language two, language three>"],
    ["languages.stack", "<frameworks, platforms, infrastructure>"],
    ["focus.now", "<what you are learning or shipping>"],
    null,
    ["interests.software", "<developer tools, systems, AI, web>"],
    ["interests.offline", "<music, photography, lifting, travel>"],
  ],
  contact: [
    ["email", "<you@example.com>"],
    ["linkedin", "<linkedin.com/in/your-handle>"],
    ["website", "<your-domain.dev>"],
  ],
};

const themes = {
  dark: {
    background: "#0d1117",
    border: "#30363d",
    portrait: "#626c76",
    heading: "#7ee787",
    key: "#d2a8ff",
    value: "#79c0ff",
    muted: "#3d444d",
  },
  light: {
    background: "#ffffff",
    border: "#d0d7de",
    portrait: "#57606a",
    heading: "#1a7f37",
    key: "#8250df",
    value: "#0969da",
    muted: "#afb8c1",
  },
};

function escapeXml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function imageToAscii() {
  // sips is built into macOS and keeps this generator dependency-free.
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

  rmSync(bmpPath, { force: true });
  return lines;
}

function portraitMarkup(lines) {
  return lines
    .map((line, index) => `<tspan x="26" y="${30 + index * 8.45}">${escapeXml(line || " ")}</tspan>`)
    .join("\n");
}

function rowMarkup([key, value], y) {
  const dots = ". ".repeat(Math.max(3, Math.floor((52 - key.length - value.length * 0.45) / 2)));
  return `<text x="616" y="${y}" xml:space="preserve"><tspan fill="var(--muted)">. </tspan><tspan fill="var(--key)">${escapeXml(key)}:</tspan><tspan fill="var(--muted)"> ${dots} </tspan><tspan fill="var(--value)">${escapeXml(value)}</tspan></text>`;
}

function buildSvg(themeName, portrait) {
  const theme = themes[themeName];
  let y = 72;
  const details = profile.sections.map((row) => {
    if (!row) {
      y += 18;
      return "";
    }
    const markup = rowMarkup(row, y);
    y += 27;
    return markup;
  }).join("\n");

  const contactRuleY = y + 10;
  y += 42;
  const contacts = profile.contact.map((row) => {
    const markup = rowMarkup(row, y);
    y += 27;
    return markup;
  }).join("\n");

  const statsY = y + 15;

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1416 692" role="img" aria-labelledby="title desc">
  <title id="title">Vaibhaav Tiwari — developer profile</title>
  <desc id="desc">Terminal-inspired developer profile with an ASCII portrait and placeholder personal details.</desc>
  <style>
    :root {
      --background: ${theme.background};
      --border: ${theme.border};
      --portrait: ${theme.portrait};
      --heading: ${theme.heading};
      --key: ${theme.key};
      --value: ${theme.value};
      --muted: ${theme.muted};
    }
    text { font-family: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 16px; }
    .portrait { font-family: Menlo, Monaco, "Courier New", monospace; font-size: 8px; font-weight: 700; fill: var(--portrait); letter-spacing: 0; }
  </style>
  <rect x="0.5" y="0.5" width="1415" height="691" rx="12" fill="var(--background)" stroke="var(--border)"/>
  <text class="portrait" xml:space="preserve">${portraitMarkup(portrait)}</text>
  <text x="616" y="36" fill="var(--heading)" font-weight="700" xml:space="preserve">${escapeXml(profile.handle)} <tspan fill="var(--muted)">──────────────────────────────────────────────────────</tspan></text>
  ${details}
  <text x="616" y="${contactRuleY}" fill="var(--muted)" xml:space="preserve">────────────────────────<tspan fill="var(--key)" font-weight="700"> contact </tspan>─────────────────────────</text>
  ${contacts}
  <text x="616" y="${statsY}" fill="var(--muted)" xml:space="preserve">──────────────────────<tspan fill="var(--key)" font-weight="700"> github activity </tspan>──────────────────────</text>
  <text x="616" y="${statsY + 29}" xml:space="preserve"><tspan fill="var(--muted)">. </tspan><tspan fill="var(--key)">profile:</tspan><tspan fill="var(--muted)"> . . . . . . . . . . . . </tspan><tspan fill="var(--value)">github.com/Vaibhaav-Tiwari</tspan></text>
</svg>\n`;
}

const portrait = imageToAscii();
for (const themeName of Object.keys(themes)) {
  writeFileSync(new URL(`./${themeName}_mode.svg`, outputDir), buildSvg(themeName, portrait));
}

console.log("Generated assets/dark_mode.svg and assets/light_mode.svg");
