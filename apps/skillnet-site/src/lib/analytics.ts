import type { Locale } from "../i18n/config";

const ANALYTICS_CONSENT_STORAGE_KEY = "skillnet:analytics-consent";

type AnalyticsParameter = string | number | boolean;
type AnalyticsParameters = Record<string, AnalyticsParameter>;

declare global {
  interface Window {
    gtag?: (command: "event", eventName: string, parameters?: AnalyticsParameters) => void;
    skillnetLoadAnalytics?: () => void;
  }
}

function hasAnalyticsConsent(): boolean {
  try {
    return window.localStorage.getItem(ANALYTICS_CONSENT_STORAGE_KEY) === "granted";
  } catch {
    return false;
  }
}

export function trackEvent(
  eventName: string,
  locale: Locale,
  parameters: AnalyticsParameters = {},
): boolean {
  if (!hasAnalyticsConsent() || typeof window.gtag !== "function") return false;

  window.gtag("event", eventName, {
    site_language: locale,
    ...parameters,
  });
  return true;
}

export function trackCta(eventName: string, ctaLocation: string, locale: Locale): void {
  trackEvent(eventName, locale, { cta_location: ctaLocation });
}
