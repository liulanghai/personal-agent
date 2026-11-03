// ESLint flat config for the web frontend and the TypeScript SDK.
// Formatting is Prettier's job; ESLint only reports correctness and hooks issues.
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['**/dist/', '**/node_modules/', 'sdk/src/schema.d.ts'] },
  {
    files: ['frontend/src/**/*.{ts,tsx}', 'sdk/src/**/*.ts'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ['frontend/src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-hooks/exhaustive-deps': 'error',
    },
  },
  {
    // TEMPORARY (S0 PR4a): the pre-split monolith has 6 known findings. PR4a only
    // formats code, so they are suppressed here; PR4b splits main.tsx into hooks and
    // components, fixes them and deletes this block.
    files: ['frontend/src/main.tsx'],
    rules: {
      'react-hooks/exhaustive-deps': 'off',
      'react-hooks/set-state-in-effect': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
);
