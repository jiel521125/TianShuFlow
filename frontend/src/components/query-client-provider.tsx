"use client";

import {
  QueryClient,
  QueryClientProvider as TanStackQueryClientProvider,
} from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Disable refetch on window focus to prevent ERR_ABORTED errors
      // when the browser cancels stale requests during rapid tab switches.
      refetchOnWindowFocus: false,
      // Cache queries for 30 seconds before they become stale.
      // This prevents redundant refetches when navigating between
      // pages that share the same data (e.g. /api/features, /api/agents).
      staleTime: 30_000,
      // Don't retry on network errors — these are usually caused by
      // request cancellation during navigation, not real failures.
      retry: (failureCount, error) => {
        // Don't retry abort or network errors
        if (error instanceof TypeError) return false;
        if (error instanceof DOMException && error.name === "AbortError") return false;
        return failureCount < 1;
      },
    },
  },
});

export function QueryClientProvider({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <TanStackQueryClientProvider client={queryClient}>
      {children}
    </TanStackQueryClientProvider>
  );
}
