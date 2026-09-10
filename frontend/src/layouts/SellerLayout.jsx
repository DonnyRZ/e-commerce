import { useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  ClipboardList,
  LayoutDashboard,
  Menu,
  Package,
  Store,
  UserCircle,
  Warehouse,
  X,
} from "lucide-react";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";

const ACCENT = "#145A46";

function NavItem({ to, icon: Icon, label, end, onClick, testId }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      data-testid={testId}
      className={({ isActive }) =>
        `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
          isActive
            ? "border-r-2 border-[#145A46] bg-[#145A46]/5 font-semibold text-[#145A46]"
            : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
        }`
      }
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </NavLink>
  );
}

export default function SellerLayout() {
  const { t } = useI18n();
  const { user, checking } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const navigate = useNavigate();

  if (checking) {
    return (
      <div className="min-h-screen bg-neutral-50 p-8" data-testid="seller-loading">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "seller") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-50" data-testid="seller-forbidden">
        <div className="text-center">
          <p className="text-sm text-neutral-500">{t("seller.forbidden")}</p>
          <button
            onClick={() => navigate("/")}
            className="mt-4 h-10 border border-neutral-300 px-6 text-sm hover:border-neutral-900"
          >
            {t("seller.backToStore")}
          </button>
        </div>
      </div>
    );
  }

  const nav = (onClick) => (
    <nav className="flex flex-col py-4">
      <NavItem to="/seller" end icon={LayoutDashboard} label={t("seller.nav.dashboard")} onClick={onClick} testId="seller-nav-dashboard" />
      <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
        {t("seller.nav.products")}
      </p>
      <NavItem to="/seller/products" icon={Package} label={t("seller.nav.productsList")} onClick={onClick} testId="seller-nav-products" />
      <NavItem to="/seller/inventory" icon={Warehouse} label={t("seller.nav.inventory")} onClick={onClick} testId="seller-nav-inventory" />
      <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
        {t("seller.nav.orders")}
      </p>
      <NavItem to="/seller/orders" icon={ClipboardList} label={t("seller.nav.ordersList")} onClick={onClick} testId="seller-nav-orders" />
      <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
        {t("seller.nav.account")}
      </p>
      <NavItem to="/seller/profile" icon={UserCircle} label={t("seller.nav.profile")} onClick={onClick} testId="seller-nav-profile" />
    </nav>
  );

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900" data-testid="seller-layout">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-neutral-200 bg-white px-4 lg:px-6">
        <button
          className="lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="menu"
          data-testid="seller-menu-open"
        >
          <Menu className="h-5 w-5" />
        </button>
        <Link to="/seller" className="flex items-center gap-2" data-testid="seller-brand">
          <Store className="h-5 w-5" style={{ color: ACCENT }} aria-hidden="true" />
          <span className="text-sm font-bold tracking-wide">MUSLIMAH CANTIK</span>
          <span className="text-xs font-medium text-neutral-400">{t("seller.portal")}</span>
        </Link>
        <div className="ml-auto flex items-center gap-3">
          <Link to="/" className="text-xs text-neutral-500 hover:text-neutral-900" data-testid="seller-view-store">
            {t("seller.backToStore")}
          </Link>
          <span className="hidden text-xs text-neutral-400 sm:block" data-testid="seller-user-email">
            {user.email}
          </span>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 border-r border-neutral-200 bg-white lg:block">
          {nav()}
        </aside>
        {drawer ? (
          <div className="fixed inset-0 z-40 lg:hidden" data-testid="seller-drawer">
            <div className="absolute inset-0 bg-black/30" onClick={() => setDrawer(false)} />
            <aside className="absolute left-0 top-0 h-full w-64 bg-white shadow-lg">
              <div className="flex h-14 items-center justify-between border-b border-neutral-200 px-4">
                <span className="text-sm font-bold">{t("seller.portal")}</span>
                <button onClick={() => setDrawer(false)} aria-label="close" data-testid="seller-menu-close">
                  <X className="h-5 w-5" />
                </button>
              </div>
              {nav(() => setDrawer(false))}
            </aside>
          </div>
        ) : null}
        <main className="min-w-0 flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
