import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no layout engine, so scrolling APIs are missing.
Element.prototype.scrollIntoView = () => {};

// Vitest globals are off, so Testing Library cannot register cleanup itself.
afterEach(() => cleanup());
