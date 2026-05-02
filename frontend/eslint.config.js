import { defineConfig } from 'eslint/config'
import js from '@eslint/js'
import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'

export default defineConfig([
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{js,mjs,cjs}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        defineProps: 'readonly',
        defineEmits: 'readonly',
        defineExpose: 'readonly',
        withDefaults: 'readonly',
      },
    },
    rules: {
      'no-console': 'off',
      'no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        ignoreRestSiblings: true,
      }],
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    // Vue-Dateien — @typescript-eslint/parser nicht installiert;
    // TS-Syntax-Checks laufen ausschließlich via vue-tsc.
    // ESLint prüft nur Vue-Template-Regeln und JS-Muster.
    files: ['**/*.vue'],
    ignores: [],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parser: vueParser,
      parserOptions: {
        // parser: false → vue-eslint-parser überspringt den <script lang="ts">-Block.
        // TS-Korrektheit wird ausschließlich via vue-tsc geprüft.
        parser: false,
      },
      globals: {
        ...globals.browser,
        ...globals.node,
        defineProps: 'readonly',
        defineEmits: 'readonly',
        defineExpose: 'readonly',
        withDefaults: 'readonly',
      },
    },
    rules: {
      'no-console': 'off',
      'no-unused-vars': 'off',
      'vue/multi-word-component-names': 'off',
    },
  },
])
