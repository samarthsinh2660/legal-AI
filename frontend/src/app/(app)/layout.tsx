import { AppSidebar } from "@/components/molecules/app-sidebar";
import { AccountMenu } from "@/features/auth/component/account-menu";
import { RequireAuth } from "@/features/auth/component/require-auth";

/** The authenticated shell. Login and register sit outside this group and
 *  so get none of it. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <RequireAuth>
      <div className="flex min-h-screen flex-1">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 items-center justify-end gap-3 border-b border-line bg-surface-card px-6">
            <AccountMenu />
          </header>
          <main className="flex-1 overflow-y-auto p-6 lg:p-8">{children}</main>
        </div>
      </div>
    </RequireAuth>
  );
}
