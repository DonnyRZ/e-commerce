import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider } from "@/i18n";
import AppShell from "@/components/layout/AppShell";
import HomePage from "@/pages/HomePage";
import ShopPage from "@/pages/ShopPage";
import PlaceholderPage from "@/pages/PlaceholderPage";

function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/shop" element={<ShopPage />} />
            <Route path="/search" element={<PlaceholderPage titleKey="page.title.search" />} />
            <Route path="/cart" element={<PlaceholderPage titleKey="page.title.cart" />} />
            <Route path="/wishlist" element={<PlaceholderPage titleKey="page.title.wishlist" />} />
            <Route path="/account" element={<PlaceholderPage titleKey="page.title.account" />} />
            <Route path="/checkout" element={<PlaceholderPage titleKey="page.title.checkout" />} />
            <Route path="/seller" element={<PlaceholderPage titleKey="page.title.seller" />} />
            <Route path="/admin" element={<PlaceholderPage titleKey="page.title.admin" />} />
            <Route path="*" element={<PlaceholderPage titleKey="errors.notFound" />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-center" richColors />
    </I18nProvider>
  );
}

export default App;
