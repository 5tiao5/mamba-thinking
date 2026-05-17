type ToggleSwitchProps = {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
};

export function ToggleSwitch({ checked, label, onChange, disabled = false }: ToggleSwitchProps) {
  return (
    <label className={`toggle-row ${disabled ? "toggle-disabled" : ""}`}>
      <button
        aria-checked={checked}
        aria-label={label}
        className={checked ? "toggle-switch toggle-on" : "toggle-switch"}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        role="switch"
        type="button"
      >
        <span />
      </button>
      <span>{label}</span>
    </label>
  );
}
