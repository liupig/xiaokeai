/// <reference types="vite/client" />

interface CompanionDesktop {
  isShell: true;
  pickFolder?: () => Promise<string>;
}

interface Window {
  companionDesktop?: CompanionDesktop;
}
