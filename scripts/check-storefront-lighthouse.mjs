#!/usr/bin/env node

import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const DEFAULT_THRESHOLD = 90;
const WEIGHTS = {
  collection: 0.43,
  home: 0.17,
  product: 0.4,
};

function parseArgs(argv) {
  const options = {
    collection: "",
    home: "",
    outputDir: ".lighthouse",
    product: "",
    threshold: DEFAULT_THRESHOLD,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];

    if (current === "--help") {
      printHelp();
      process.exit(0);
    }
    if (current === "--home" && next) {
      options.home = next;
      index += 1;
      continue;
    }
    if (current === "--product" && next) {
      options.product = next;
      index += 1;
      continue;
    }
    if (current === "--collection" && next) {
      options.collection = next;
      index += 1;
      continue;
    }
    if (current === "--output-dir" && next) {
      options.outputDir = next;
      index += 1;
      continue;
    }
    if (current === "--threshold" && next) {
      options.threshold = Number(next);
      index += 1;
      continue;
    }
  }

  return options;
}

function printHelp() {
  console.log(`Usage:
  npm run perf:storefront -- --home <url> --product <url> --collection <url> [--threshold 90]

This runs Lighthouse against the three pages Shopify weights for storefront impact:
home (17%), product (40%), and collection (43%).

Requirements:
  - A local Chrome installation
  - Lighthouse CLI available on PATH
`);
}

function assertCliInstalled() {
  const versionCheck = spawnSync("lighthouse", ["--version"], { encoding: "utf8" });
  if (versionCheck.status !== 0) {
    console.error("Missing `lighthouse` CLI. Install it locally or globally before running this check.");
    process.exit(1);
  }
}

function runAudit(label, url, outputDir) {
  const outputPath = resolve(outputDir, `${label}.json`);
  const result = spawnSync(
    "lighthouse",
    [
      url,
      "--quiet",
      "--chrome-flags=--headless=new",
      "--only-categories=performance",
      "--output=json",
      `--output-path=${outputPath}`,
    ],
    { encoding: "utf8", stdio: "pipe" },
  );

  if (result.status !== 0) {
    console.error(result.stderr || result.stdout || `Lighthouse failed for ${label}.`);
    process.exit(result.status ?? 1);
  }

  const report = JSON.parse(readFileSync(outputPath, "utf8"));
  const score = Number(report.categories.performance.score) * 100;
  return { outputPath, score };
}

function assertUrls(options) {
  if (!options.home || !options.product || !options.collection) {
    printHelp();
    console.error("All of --home, --product, and --collection are required.");
    process.exit(1);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  assertUrls(options);
  assertCliInstalled();

  mkdirSync(resolve(options.outputDir), { recursive: true });

  const scores = {
    collection: runAudit("collection", options.collection, options.outputDir),
    home: runAudit("home", options.home, options.outputDir),
    product: runAudit("product", options.product, options.outputDir),
  };

  const weightedScore =
    scores.home.score * WEIGHTS.home +
    scores.product.score * WEIGHTS.product +
    scores.collection.score * WEIGHTS.collection;

  console.log(`Home: ${scores.home.score.toFixed(1)} (${scores.home.outputPath})`);
  console.log(`Product: ${scores.product.score.toFixed(1)} (${scores.product.outputPath})`);
  console.log(`Collection: ${scores.collection.score.toFixed(1)} (${scores.collection.outputPath})`);
  console.log(`Weighted score: ${weightedScore.toFixed(1)}`);

  if (weightedScore < options.threshold) {
    console.error(
      `Weighted storefront performance score ${weightedScore.toFixed(1)} is below threshold ${options.threshold}.`,
    );
    process.exit(1);
  }
}

main();
