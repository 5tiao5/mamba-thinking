type SegmentOption = {
  value: string;
  label: string;
};

type SegmentedControlProps = {
  value: string;
  options: SegmentOption[];
  onChange: (value: string) => void;
  label?: string;
};

export function SegmentedControl({ value, options, onChange, label }: SegmentedControlProps) {
  return (
    <div className="segmented-control" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          className={option.value === value ? "segment segment-active" : "segment"}
          key={option.value}
          onClick={() => onChange(option.value)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
