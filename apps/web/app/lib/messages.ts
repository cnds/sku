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
    subtitle: "AI-powered product performance ranking",
    viewTopProduct: "View top product",
    bannerText: (count: number, window: string) =>
      `Tracking ${count} products for ${window}. SKU Lens ranks products into Red Board (hidden gems) and Black Board (underperformers).`,
    errorMessage: "Failed to load the dashboard. The analytics server may be unavailable.",
    blackboardTitle: "Black Board",
    blackboardSubtitle: "High views, low conversion",
    redboardTitle: "Red Board",
    redboardSubtitle: "High conversion, low traffic",
  },

  product: {
    backAction: "Board",
    errorTitle: "Product Analysis",
    errorMessage: "Failed to load product analysis. The product may not exist or the server is unavailable.",
    notFound: "This product was not found.",
    subtitle: (benchmark: string) => `Scoring & AI diagnosis · benchmark: ${benchmark}`,
  },

  leaderboard: {
    resourceSingular: "product",
    resourcePlural: "products",
    emptyHeading: (title: string) => `No ${title.toLowerCase()} products yet`,
    emptyDescription: "Products will appear here once enough engagement data has been collected.",
    columnRank: "#",
    columnProduct: "Product",
    columnViews: "Views",
    columnAddToCart: "Add to Cart",
    columnOrders: "Orders",
    columnScore: "Score",
    productCount: (count: number) => `${count} ${count === 1 ? "product" : "products"}`,
  },

  analysis: {
    scoringHeading: "Scoring Dimensions",
    diagnosisHeading: "AI Diagnosis",
    diagnosisGenerating: "Generating",
    diagnosisFailed: "Failed",
    diagnosisReady: "Ready",
    diagnosisPendingBanner: "The AI is analyzing this product. This usually takes 10–30 seconds.",
    diagnosisFailedFallback: "Diagnosis failed unexpectedly.",
    diagnosisNoReport: "No report available.",
    cardProblem: "Problem Diagnosis",
    cardCause: "Root Cause",
    cardRecommendations: "Recommendations",
    dimensionViews: "Views",
    dimensionAddToCart: "Add to Cart",
    dimensionOrders: "Orders",
    dimensionCtr: "CTR",
    dimensionConversion: "Conversion",
  },

  timeWindows: {
    "24h": "24 Hours",
    "7d": "7 Days",
    "30d": "30 Days",
  },

  componentLabels: {
    description: "Description",
    review_tab: "Review Tab",
    size_chart: "Size Chart",
  } as Record<string, string>,
} as const;
