import React from "react";
import BrandLogo from "@/components/brand/BrandLogo";

export default class ErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Keep production failures visible in the browser console/observability
    // pipeline without exposing stack traces to shoppers.
    console.error("Uncaught storefront error", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-center">
        <div className="max-w-md">
          <div className="mb-8 flex justify-center">
            <BrandLogo variant="mark" size="lg" to={null} testId="error-brand-logo" priority />
          </div>
          <h1 className="text-2xl font-semibold">Halaman mengalami kendala</h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Muat ulang halaman untuk melanjutkan. Keranjang dan pesanan Anda tetap aman.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-6 inline-flex h-11 items-center bg-foreground px-8 text-sm font-semibold text-background hover:bg-primary"
          >
            Muat ulang
          </button>
        </div>
      </main>
    );
  }
}
