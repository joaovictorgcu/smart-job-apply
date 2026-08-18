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
  overrides: [
    {
      // Context providers intentionally ship their provider and their hook side
      // by side, which fast refresh cannot support. The trade-off is deliberate.
      files: ["src/hooks/**/*.tsx", "src/lib/**/*.tsx"],
      rules: { "react-refresh/only-export-components": "off" },
    },
    {
      // Vitest injects these; the test files still import them explicitly, so
      // this only stops no-undef from flagging the ones Testing Library uses.
      files: ["src/**/*.test.ts", "src/**/*.test.tsx", "src/test/**/*.{ts,tsx}"],
      env: { node: true },
      globals: {
        afterAll: "readonly",
        afterEach: "readonly",
        beforeAll: "readonly",
        beforeEach: "readonly",
        describe: "readonly",
        expect: "readonly",
        it: "readonly",
        vi: "readonly",
      },
    },
  ],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "@typescript-eslint/consistent-type-imports": ["warn", { prefer: "type-imports" }],
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "no-console": ["warn", { allow: ["warn", "error"] }],
  },
};
