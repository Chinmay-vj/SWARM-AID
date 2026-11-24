/**
 * Native <dialog> based modal and drawer: the browser provides focus trapping, Escape to close
 * and inert background. Focus returns to the opener when closed.
 */
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./primitives";

function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<Element | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      opener.current = document.activeElement;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      if (opener.current instanceof HTMLElement) opener.current.focus();
    }
  }, [open]);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const cancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", cancel);
    return () => dialog.removeEventListener("cancel", cancel);
  }, [onClose]);
  return ref;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useDialog(open, onClose);
  const titleId = useId();
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      style={wide ? { width: "min(860px, calc(100vw - 32px))" } : undefined}
    >
      {open && (
        <>
          <div className="modal-head">
            <h2 id={titleId}>{title}</h2>
            <Button
              variant="ghost"
              aria-label="Close dialog"
              icon={<X size={16} aria-hidden="true" />}
              onClick={onClose}
            />
          </div>
          <div className="modal-body">{children}</div>
          {footer && <div className="modal-foot">{footer}</div>}
        </>
      )}
    </dialog>
  );
}

export function Drawer({
  open,
  onClose,
  title,
  children,
  actions,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const ref = useDialog(open, onClose);
  const titleId = useId();
  return (
    <dialog ref={ref} className="drawer" aria-labelledby={titleId}>
      {open && (
        <>
          <div
            className="modal-head row between"
            style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}
          >
            <h2 id={titleId}>{title}</h2>
            <div className="row">
              {actions}
              <Button
                variant="ghost"
                aria-label="Close panel"
                icon={<X size={16} aria-hidden="true" />}
                onClick={onClose}
              />
            </div>
          </div>
          <div className="drawer-body">{children}</div>
        </>
      )}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  tone = "primary",
  busy,
  onConfirm,
  onCancel,
  disabled,
}: {
  open: boolean;
  title: ReactNode;
  children: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "ok" | "bad" | "warn";
  busy?: boolean;
  disabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onCancel}
      title={title}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone} onClick={onConfirm} disabled={busy || disabled} aria-busy={busy}>
            {busy ? "Submitting…" : confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
