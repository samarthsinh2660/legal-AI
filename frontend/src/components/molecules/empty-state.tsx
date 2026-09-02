export function EmptyState({ message }: { message: string }) {
  return (
    <p className="px-4 py-8 text-center text-sm text-ink-muted">{message}</p>
  );
}
