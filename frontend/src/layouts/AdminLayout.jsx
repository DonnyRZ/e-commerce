import { useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  ClipboardList,
  FileText,
  FolderTree,
  Image,
  LayoutDashboard,
  Menu,
  Package,
  Settings,
  ShieldAlert,
  Store,
  Users,
  X,
} from "lucide-react";
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

function NavGroup({ label }) {
  return (
    <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
      {label}
    </p>
  );
}

export default function AdminLayout() {
  const { user, checking } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const navigate = useNavigate();

  if (checking) {
    return (
      <div className="min-h-screen bg-neutral-50 p-8" data-testid="admin-loading">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-50" data-testid="admin-forbidden">
        <div className="text-center">
          <p className="text-sm text-neutral-500">This area is for the store administrator only.</p>
          <button
            onClick={() => navigate("/")}
            data-testid="admin-forbidden-back"
            className="mt-4 h-10 border border-neutral-300 px-6 text-sm hover:border-neutral-900"
          >
            Back to store
          </button>
        </div>
      </div>
    );
  }

  const nav = (onClick) => (
    <nav className="flex flex-col py-4">
      <NavItem to="/admin" end icon={LayoutDashboard} label="Dashboard" onClick={onClick} testId="admin-nav-dashboard" />
      <NavGroup label="Catalog" />
      <NavItem to="/admin/products" icon={Package} label="Products" onClick={onClick} testId="admin-nav-products" />
      <NavItem to="/admin/categories" icon={FolderTree} label="Categories" onClick={onClick} testId="admin-nav-categories" />
      <NavGroup label="Sales" />
      <NavItem to="/admin/orders" icon={ClipboardList} label="Orders" onClick={onClick} testId="admin-nav-orders" />
      <NavItem to="/admin/payments" icon={ShieldAlert} label="Payment Review" onClick={onClick} testId="admin-nav-payments" />
      <NavItem to="/admin/customers" icon={Users} label="Customers" onClick={onClick} testId="admin-nav-customers" />
      <NavGroup label="CMS" />
      <NavItem to="/admin/cms" icon={FileText} label="Content" onClick={onClick} testId="admin-nav-cms" />
      <NavItem to="/admin/media" icon={Image} label="Media Library" onClick={onClick} testId="admin-nav-media" />
      <NavGroup label="System" />
      <NavItem to="/admin/settings" icon={Settings} label="Settings" onClick={onClick} testId="admin-nav-settings" />
    </nav>
  );

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900" data-testid="admin-layout">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-neutral-200 bg-white px-4 lg:px-6">
        <button
          className="lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="menu"
          data-testid="admin-menu-open"
        >
          <Menu className="h-5 w-5" />
        </button>
        <Link to="/admin" className="flex items-center gap-2" data-testid="admin-brand">
          <Store className="h-5 w-5" style={{ color: ACCENT }} aria-hidden="true" />
          <span className="text-sm font-bold tracking-wide">MUSLIMAH CANTIK</span>
          <span className="text-xs font-medium text-neutral-400">Admin</span>
        </Link>
        <div className="ml-auto flex items-center gap-3">
          <Link to="/" className="text-xs text-neutral-500 hover:text-neutral-900" data-testid="admin-view-store">
            View Store
          </Link>
          <span className="hidden text-xs text-neutral-400 sm:block" data-testid="admin-user-email">
            {user.email}
          </span>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 border-r border-neutral-200 bg-white lg:block">
          {nav()}
        </aside>
        {drawer ? (
          <div className="fixed inset-0 z-40 lg:hidden" data-testid="admin-drawer">
            <div className="absolute inset-0 bg-black/30" onClick={() => setDrawer(false)} />
            <aside className="absolute left-0 top-0 h-full w-64 bg-white shadow-lg">
              <div className="flex h-14 items-center justify-between border-b border-neutral-200 px-4">
                <span className="text-sm font-bold">Admin</span>
                <button onClick={() => setDrawer(false)} aria-label="close" data-testid="admin-menu-close">
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
