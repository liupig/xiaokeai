'use strict';

const fs = require('node:fs');
const path = require('node:path');

// Release packs carry the same directory next to main.js.
const root = fs.existsSync(path.join(__dirname, 'branding', 'brand.json'))
  ? path.join(__dirname, 'branding')
  : path.join(__dirname, '..', 'frontend', 'public', 'branding');
const brand = JSON.parse(fs.readFileSync(path.join(root, 'brand.json'), 'utf8'));

function getLogoPath(variant = brand.defaultLogo) {
  if (!Object.hasOwn(brand.logos, variant)) throw new Error(`Unknown logo: ${variant}`);
  return path.join(root, brand.logos[variant].file);
}

module.exports = { getLogoPath, brand };
