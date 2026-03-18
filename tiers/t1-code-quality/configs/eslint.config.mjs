// Org default: ESLint flat config
// Copied by harness install when no ESLint config exists in target repo.

import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-console": "warn",
    },
  },
  {
    ignores: ["node_modules/", ".next/", "dist/", "build/"],
  },
];
