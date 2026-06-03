import KagentLogo from "./kagent-logo";

export function Footer() {
  return (
    <footer className="mt-auto py-5">
      <div className="text-center text-sm text-muted-foreground flex items-center justify-center gap-2">
        <KagentLogo animate={true} className="h-6 w-6 text-[#942DE7]" />
        <p>is an open source project</p>
      </div>
    </footer>
  );
}
