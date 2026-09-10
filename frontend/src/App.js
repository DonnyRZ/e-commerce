import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider } from "@/i18n";
import { AuthProvider } from "@/lib/AuthContext";
import { ShopProvider } from "@/lib/ShopContext";
import AppShell from "@/components/layout/AppShell";
import HomePage from "@/pages/HomePage";
import ShopPage from "@/pages/ShopPage";
import SearchPage from "@/pages/SearchPage";
import ProductPage from "@/pages/ProductPage";
import CmsPublicPage from "@/pages/CmsPublicPage";
import FaqPage from "@/pages/FaqPage";
import PlaceholderPage from "@/pages/PlaceholderPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import AccountPage from "@/pages/AccountPage";
import CartPage from "@/pages/CartPage";
import WishlistPage from "@/pages/WishlistPage";
import CheckoutPage from "@/pages/CheckoutPage";
import MockPaymentPage from "@/pages/MockPaymentPage";
import PaymentPendingPage from "@/pages/PaymentPendingPage";
import OrderConfirmationPage from "@/pages/OrderConfirmationPage";
import OrdersPage from "@/pages/OrdersPage";
import OrderDetailPage from "@/pages/OrderDetailPage";
import AdminLayout from "@/layouts/AdminLayout";
import AdminDashboardPage from "@/pages/admin/AdminDashboardPage";
import AdminProductsPage from "@/pages/admin/AdminProductsPage";
import AdminProductEditPage from "@/pages/admin/AdminProductEditPage";
import AdminCategoriesPage from "@/pages/admin/AdminCategoriesPage";
import AdminOrdersPage from "@/pages/admin/AdminOrdersPage";
import AdminOrderDetailPage from "@/pages/admin/AdminOrderDetailPage";
import AdminCustomersPage from "@/pages/admin/AdminCustomersPage";
import AdminPaymentsPage from "@/pages/admin/AdminPaymentsPage";
import CmsContentPage from "@/pages/admin/CmsContentPage";
import CmsContentEditPage from "@/pages/admin/CmsContentEditPage";
import CmsMediaPage from "@/pages/admin/CmsMediaPage";
import AdminSettingsPage from "@/pages/admin/AdminSettingsPage";

function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <ShopProvider>
          <BrowserRouter>
          <Routes>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminDashboardPage />} />
              <Route path="products" element={<AdminProductsPage />} />
              <Route path="products/new" element={<AdminProductEditPage />} />
              <Route path="products/:productId" element={<AdminProductEditPage />} />
              <Route path="categories" element={<AdminCategoriesPage />} />
              <Route path="orders" element={<AdminOrdersPage />} />
              <Route path="orders/:orderNumber" element={<AdminOrderDetailPage />} />
              <Route path="customers" element={<AdminCustomersPage />} />
              <Route path="payments" element={<AdminPaymentsPage />} />
              <Route path="cms" element={<CmsContentPage />} />
              <Route path="cms/new" element={<CmsContentEditPage />} />
              <Route path="cms/:entryId" element={<CmsContentEditPage />} />
              <Route path="media" element={<CmsMediaPage />} />
              <Route path="settings" element={<AdminSettingsPage />} />
            </Route>
            <Route element={<AppShell />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/shop" element={<ShopPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/product/:slug" element={<ProductPage />} />
              <Route path="/page/:slug" element={<CmsPublicPage />} />
              <Route path="/faq" element={<FaqPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/account" element={<AccountPage />} />
              <Route path="/cart" element={<CartPage />} />
              <Route path="/wishlist" element={<WishlistPage />} />
              <Route path="/orders" element={<OrdersPage />} />
              <Route path="/orders/:orderNumber" element={<OrderDetailPage />} />
              <Route path="/checkout" element={<CheckoutPage />} />
              <Route path="/checkout/payment/mock" element={<MockPaymentPage />} />
              <Route path="/payment-pending" element={<PaymentPendingPage />} />
              <Route path="/order-confirmation" element={<OrderConfirmationPage />} />
              <Route path="*" element={<PlaceholderPage titleKey="errors.notFound" />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors />
        </ShopProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

export default App;
