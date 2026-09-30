import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import "@/index.css";
import CmsApp from "./App";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import { subscribeToProductUpdates } from "@/lib/productUpdateEvents";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

function ProductUpdateCacheBridge() {
  const queryClient = useQueryClient();
  useEffect(
    () => subscribeToProductUpdates(() => {
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["admin-product"] });
    }),
    [queryClient],
  );
  return null;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ProductUpdateCacheBridge />
      <ErrorBoundary>
        <CmsApp />
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>,
);
