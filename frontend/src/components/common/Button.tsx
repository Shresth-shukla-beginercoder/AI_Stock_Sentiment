import { ButtonHTMLAttributes, forwardRef } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className = "", children, ...props }, ref) => {
    const baseStyles = "inline-flex items-center justify-center font-medium rounded-lg transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-glow-blue focus-visible:ring-offset-2 focus-visible:ring-offset-ink disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-[0.98]";

    const variants = {
      primary: "bg-gradient-to-r from-glow-blue to-bell-amber text-ink font-semibold shadow-[0_4px_15px_rgba(59,130,246,0.3)] hover:shadow-[0_6px_25px_rgba(59,130,246,0.4)] hover:-translate-y-0.5",
      secondary: "border border-glow-blue/40 text-glow-blue hover:bg-glow-blue/10 hover:border-glow-blue/60",
      ghost: "text-muted hover:text-text-primary hover:bg-white/5",
      danger: "bg-gradient-to-r from-danger to-danger-bright text-white shadow-[0_4px_15px_rgba(239,68,68,0.3)] hover:shadow-[0_6px_25px_rgba(239,68,68,0.4)]",
    };

    const sizes = {
      sm: "px-3 py-1.5 text-xs",
      md: "px-4 py-2 text-sm",
      lg: "px-6 py-3 text-base",
    };

    return (
      <button
        ref={ref}
        className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
