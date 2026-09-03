/// <reference types="vite/client" />

interface CompanionDesktop {
  isShell: true;
}

interface Window {
  companionDesktop?: CompanionDesktop;
}
