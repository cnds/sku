// All user-facing strings live here.
// When adding i18n, replace this module with a locale-aware lookup
// (e.g. @shopify/react-i18n or react-intl) — every consumer already
// imports from this single file, so no component changes are needed.

export const messages = {
  app: {
    name: "SKU Lens",
  },

  errors: {
    pageNotFound: "The page you're looking for doesn't exist.",
    somethingWentWrong: "Something went wrong",
    unexpectedError: "An unexpected error occurred. Please try refreshing the page.",
  },

  dashboard: {
    subtitle: "Daily decision board for product priorities",
    viewTopProduct: "View top priority",
    bannerText: (count: number, window: string) =>
      `Tracking ${count} products for ${window}. SKU Lens prioritizes Winners and Leakers for this window.`,
    prioritiesTitle: "Today's product priorities",
    prioritiesSubtitle: "Two Leakers to fix first and one Hidden Winner to scale when the signal is ready.",
    prioritiesEmpty: "Priority cards will appear once storefront and PDP events are collected.",
    viewMoreProducts: "View more products",
    errorMessage: "Failed to load the board. The analytics server may be unavailable.",
    blackboardTitle: "Leakers",
    blackboardSubtitle: "High attention, weak progression",
    redboardTitle: "Winners",
    redboardSubtitle: "High intent, underexposed",
  },

  product: {
    backAction: "Board",
    errorTitle: "Product Analysis",
    errorMessage: "Failed to load product analysis. The product may not exist or the server is unavailable.",
    notFound: "This product was not found.",
    subtitle: (benchmark: string) => `Shopper journey and diagnosis · benchmark: ${benchmark}`,
  },

  leaderboard: {
    resourceSingular: "product",
    resourcePlural: "products",
    emptyHeading: (title: string) => `No ${title.toLowerCase()} products yet`,
    emptyDescription: "Products will appear here once enough engagement data has been collected.",
    columnProduct: "Product",
    columnSignal: "Recent signal",
    productCount: (count: number) => `${count} ${count === 1 ? "product" : "products"}`,
  },

  analysis: {
    journeyHeading: "Shopper Journey",
    primaryDropOff: "Primary drop-off",
    diagnosisHeading: "AI Diagnosis",
    diagnosisGenerating: "Generating",
    diagnosisFailed: "Failed",
    diagnosisReady: "Ready",
    diagnosisPendingBanner: "The AI is analyzing this product. This usually takes 10–30 seconds.",
    diagnosisFailedFallback: "Diagnosis failed unexpectedly.",
    diagnosisNoReport: "No report available.",
    cardObserved: "Observed",
    cardEvidence: "Evidence",
    cardSuspectedFriction: "Suspected friction",
    cardFirstFix: "First fix to try",
    dimensionExposure: "Exposure",
    dimensionClick: "Click",
    dimensionPdpView: "PDP view",
    dimensionEngagement: "Engagement",
    dimensionAddToCart: "Add to cart",
    dimensionOrders: "Order",
  },

  timeWindows: {
    "24h": "24 Hours",
    "7d": "7 Days",
    "30d": "30 Days",
  },

} as const;
