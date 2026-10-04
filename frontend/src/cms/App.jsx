import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider } from "@/i18n";
import { AuthProvider, useAuth } from "@/lib/AuthContext";
import AdminLayout from "@/layouts/AdminLayout";
import AdminLoginPage from "@/pages/admin/AdminLoginPage";
import AdminDashboardPage from "@/pages/admin/AdminDashboardPage";
import AdminProductsPage from "@/pages/admin/AdminProductsPage";
import AdminProductEditPage from "@/pages/admin/AdminProductEditPage";
import AdminCategoriesPage from "@/pages/admin/AdminCategoriesPage";
import AdminOrdersPage from "@/pages/admin/AdminOrdersPage";
import AdminOrderDetailPage from "@/pages/admin/AdminOrderDetailPage";
import AdminInquiryDetailPage from "@/pages/admin/AdminInquiryDetailPage";
import AdminCustomersPage from "@/pages/admin/AdminCustomersPage";
import CmsContentPage from "@/pages/admin/CmsContentPage";
import CmsContentEditPage from "@/pages/admin/CmsContentEditPage";
import { CmsHelpWorkspace, CmsHomepageWorkspace, CmsNavigationWorkspace, CmsStoriesWorkspace } from "@/pages/admin/CmsContentWorkspacePages";
import CmsMediaPage from "@/pages/admin/CmsMediaPage";
import AdminSettingsPage from "@/pages/admin/AdminSettingsPage";
import AdminTelegramInboxPage from "@/pages/admin/AdminTelegramInboxPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import { Skeleton } from "@/components/ui/skeleton";
import CmsDeviceProvider from "./CmsDeviceProvider";

function AdminLoading() {
  return (
    <div className="min-h-screen bg-neutral-50 p-8" data-testid="admin-loading">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="mt-6 h-64 w-full" />
    </div>
  );
}

function AdminForbidden() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-neutral-50 px-6 text-neutral-900"
      data-testid="admin-forbidden"
    >
      <div className="max-w-md text-center">
        <p className="text-sm text-neutral-500">
          This area is for the store administrator only.
        </p>
        <a
          href="/"
          data-testid="admin-forbidden-back"
          className="mt-4 inline-flex h-10 items-center border border-neutral-300 px-6 text-sm hover:border-neutral-900"
        >
          Back to store
        </a>
      </div>
    </div>
  );
}

function ProtectedAdminLayout() {
  const { user, checking } = useAuth();
  const location = useLocation();

  if (checking) return <AdminLoading />;

  if (!user) {
    // /admin is the CMS login surface. Deep links return there instead of
    // leaking the storefront login or leaving the user at a dead route.
    if (location.pathname === "/") return <AdminLoginPage />;
    return <Navigate to="/" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }

  if (user.role !== "admin") return <AdminForbidden />;

  return <AdminLayout />;
}

function CmsRoutes() {
  return (
    <Routes>
      <Route path="forgot-password" element={<ForgotPasswordPage backTo="/" brandTo="/" />} />
      <Route path="reset-password" element={<ResetPasswordPage backTo="/" brandTo="/" />} />
      <Route element={<ProtectedAdminLayout />}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="products" element={<AdminProductsPage />} />
        <Route path="products/new" element={<AdminProductEditPage />} />
        <Route path="products/:productId" element={<AdminProductEditPage />} />
        <Route path="categories" element={<AdminCategoriesPage />} />
        <Route path="orders" element={<AdminOrdersPage />} />
        <Route path="orders/inquiry/:reference" element={<AdminInquiryDetailPage />} />
        <Route path="orders/:orderNumber" element={<AdminOrderDetailPage />} />
        <Route path="telegram-inbox" element={<AdminTelegramInboxPage />} />
        <Route path="telegram-inquiries" element={<Navigate to="/orders?stage=inquiry" replace />} />
        <Route path="payments" element={<Navigate to="/orders?stage=payment" replace />} />
        <Route path="customers" element={<AdminCustomersPage />} />
        <Route path="cms" element={<CmsContentPage />} />
        <Route path="cms/homepage" element={<CmsHomepageWorkspace />} />
        <Route path="cms/stories" element={<CmsStoriesWorkspace />} />
        <Route path="cms/help" element={<CmsHelpWorkspace />} />
        <Route path="cms/navigation" element={<CmsNavigationWorkspace />} />
        <Route path="cms/new" element={<CmsContentEditPage />} />
        <Route path="cms/:entryId" element={<CmsContentEditPage />} />
        <Route path="media" element={<CmsMediaPage />} />
        <Route path="settings" element={<AdminSettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function CmsApp() {
  return (
    <I18nProvider>
      <AuthProvider mergeCustomerCartOnRestore={false}>
        <CmsDeviceProvider>
          <BrowserRouter basename="/admin/">
            <CmsRoutes />
          </BrowserRouter>
        </CmsDeviceProvider>
        <Toaster position="top-center" richColors />
      </AuthProvider>
    </I18nProvider>
  );
}
