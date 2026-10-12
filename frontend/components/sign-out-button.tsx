"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function SignOutButton() {
  const router = useRouter();
  async function signOut() {
    // A 401 here just means the session had already ended; either way we go to the login page.
    await fetch("/auth/logout", { method: "POST", headers: { "X-Requested-With": "web" } });
    router.replace("/login");
    router.refresh();
  }
  return (
    <Button variant="outline" onClick={signOut}>
      Sign out
    </Button>
  );
}
