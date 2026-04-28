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
    subtitle: "AI-powered winner & loser analysis",
    viewTopProduct: "View top product",
    bannerText: (count: number, window: string) =>
      `Tracking ${count} products for ${window}. SKU Lens audits product pages by measuring component-level engagement and quantifying order gaps against benchmarks.`,
    errorMessage: "Failed to load the dashboard. The analytics server may be unavailable.",
    statUnderperformers: "Underperformers",
    statUnderperformersDesc: "Products with high views but low conversion",
    statHiddenGems: "Hidden Gems",
    statHiddenGemsDesc: "Products with high conversion but low traffic",
    blackboardTitle: "Blackboard — Underperformers",
    redboardTitle: "Redboard — Hidden Gems",
  },

  product: {
    backAction: "Leaderboard",
    errorTitle: "Product Analysis",
    errorMessage: "Failed to load product analysis. The product may not exist or the server is unavailable.",
    notFound: "This product was not found.",
    gapDescription: (gap: string, sign: string) =>
      `This product has an order gap of ${sign}${gap} compared to its benchmark. Review the funnel comparison and component engagement below to identify improvement opportunities.`,
    subtitle: (benchmark: string) => `Deep-dive analysis comparing against ${benchmark}`,
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
    funnelHeading: "Funnel Comparison",
    benchmarkLabel: (id: string) => `Benchmark: ${id}`,
    metricViews: "Views",
    metricAddToCart: "Add to Cart",
    metricOrders: "Orders",
    metricVs: (value: string) => `vs ${value}`,
    diagnosisHeading: "AI Diagnosis",
    diagnosisGenerating: "Generating",
    diagnosisFailed: "Failed",
    diagnosisReady: "Ready",
    diagnosisPendingBanner: "The AI is analyzing this product. This usually takes 10–30 seconds.",
    diagnosisFailedFallback: "Diagnosis failed unexpectedly.",
    diagnosisNoReport: "No report available.",
    componentHeading: "Component Engagement",
    componentDescription: "Click-through rates compared against the benchmark product.",
    componentColumnName: "Component",
    componentColumnTargetCtr: "Target CTR",
    componentColumnBenchmarkCtr: "Benchmark CTR",
    componentColumnDelta: "Delta",
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
