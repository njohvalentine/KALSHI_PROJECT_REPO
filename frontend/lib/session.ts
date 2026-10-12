import "server-only";
import { redirect } from "next/navigation";
import { backendFetch } from "@/lib/backend";

/** The real sign-in check. The backend decides; the proxy file is only a convenience redirect. */
export async function verifySession(): Promise<{ email: string }> {
  const res = await backendFetch("/auth/me");
  if (res.status === 401) redirect("/login");
  if (!res.ok) throw new Error(`Sign-in check failed with HTTP ${res.status}`);
  return res.json();
}
