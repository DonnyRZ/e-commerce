import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { trackOrder } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { StatusBadge } from "@/pages/OrdersPage";
import { Skeleton } from "@/components/ui/skeleton";

export default function GuestOrderPage() {
  const [params] = useSearchParams();
  const orderNumber = params.get("order_number");
  const token = params.get("token");
  const query = useQuery({ queryKey: ["guest-order", orderNumber, token], queryFn: () => trackOrder(orderNumber, token), enabled: Boolean(orderNumber && token), retry: false });
  if (query.isLoading) return <div className="py-12"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-64 w-full" /></div>;
  if (query.isError || !query.data) return <div className="py-16 text-center"><h1 className="text-xl font-semibold">Order tidak ditemukan</h1><p className="mt-2 text-sm text-muted-foreground">Tautan tracking mungkin sudah tidak valid.</p><Link to="/" className="mt-6 inline-flex h-10 items-center bg-foreground px-5 text-sm font-semibold text-background">Kembali ke toko</Link></div>;
  const order = query.data;
  return <div className="py-8 lg:py-12" data-testid="guest-order-page"><p className="text-xs uppercase tracking-wide text-muted-foreground">Telegram order</p><div className="mt-2 flex flex-wrap items-center gap-3"><h1 className="text-2xl font-semibold">Order {order.order_number}</h1><StatusBadge value={order.status} kind="state" /></div><div className="mt-6 border border-border bg-secondary/30 p-5"><h2 className="text-sm font-semibold">Progress pesanan</h2><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{(order.timeline || []).map((event) => <div key={event.stage} className="text-xs"><span className="font-medium">{event.stage.replaceAll("_", " ")}</span>{event.expected_at ? <p className="mt-1 text-muted-foreground">Estimasi {new Date(event.expected_at).toLocaleDateString()}</p> : null}{event.tracking_number ? <p className="mt-1 text-muted-foreground">Resi: {event.tracking_number}</p> : null}</div>)}</div></div><div className="mt-8 divide-y divide-border border-y border-border">{(order.items || []).map((item) => <div key={item.sku} className="flex gap-3 py-4">{item.image_url ? <ImageWithFallback src={item.image_url} alt="" className="h-16 w-16 object-cover" /> : null}<div className="flex-1"><p className="text-sm font-medium">{item.product_name}</p><p className="text-xs text-muted-foreground">{item.quantity} × <PriceDisplay amount={item.unit_price} /></p></div><PriceDisplay amount={item.line_total} /></div>)}</div><div className="mt-5 flex justify-between text-sm font-semibold"><span>Total</span><PriceDisplay amount={order.grand_total} /></div></div>;
}
