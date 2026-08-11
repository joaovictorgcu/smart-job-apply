/* eslint-env node */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
  },
  plugins: ["@typescript-eslint", "react-refresh"],
  ignorePatterns: ["dist", "node_modules", "*.cjs", "*.config.js"],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "@typescript-eslint/consistent-type-imports": ["warn", { prefer: "type-imports" }],
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "no-console": ["warn", { allow: ["warn", "error"] }],
  },
};
