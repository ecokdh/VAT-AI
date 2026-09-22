interface FilterChipsProps {
  options: string[];
  active: string;
  onChange: (value: string) => void;
  variant?: "primary" | "sales";
}

export function FilterChips({ options, active, onChange, variant = "primary" }: FilterChipsProps) {
  return (
    <div className="chip-row">
      {options.map((option) => {
        const isActive = option === active;
        const className = ["chip", isActive && "chip--active", isActive && variant === "sales" && "chip--sales"]
          .filter(Boolean)
          .join(" ");
        return (
          <button key={option} className={className} onClick={() => onChange(option)}>
            {option}
          </button>
        );
      })}
    </div>
  );
}
