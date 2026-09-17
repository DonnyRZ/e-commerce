import { toast } from "sonner";
import { addWishlistItem } from "./api";

export function getCustomerReturnTo(state) {
  const path = state?.returnTo;
  return typeof path === "string" &&
    path.startsWith("/") &&
    !path.startsWith("//") &&
    !path.includes("\\")
    ? path
    : "/account";
}

export async function completeCustomerAuth({ state, user, queryClient, navigate, t }) {
  const intent = state?.intent;
  if (intent?.type === "wishlist_add" && typeof intent.productId === "string") {
    try {
      await addWishlistItem(intent.productId);
      await queryClient.invalidateQueries({ queryKey: ["wishlist", user.id] });
      toast.success(t("wishlist.added"));
    } catch {
      toast.error(t("wishlist.saveAfterLoginFailed"));
    }
  }

  navigate(getCustomerReturnTo(state), { replace: true });
}
