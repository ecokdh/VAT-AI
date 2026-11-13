import { useState, type InputHTMLAttributes } from "react";

// 숫자 입력: 화면에는 세 자리마다 쉼표를 붙여 보여 주고, 값(onChange·name 전송)은 쉼표 없는 숫자 문자열로 다룬다.
type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "type"> & {
  value?: string | number | null;
  defaultValue?: string | number | null;
  onValueChange?: (raw: string) => void;
  allowDecimal?: boolean;
  allowNegative?: boolean;
};

export function NumberInput({ value, defaultValue, onValueChange, allowDecimal = false, allowNegative = false, name, ...rest }: Props) {
  const [own, setOwn] = useState(toRaw(defaultValue, allowDecimal, allowNegative));
  const raw = value === undefined ? own : toRaw(value, allowDecimal, allowNegative);
  return <>
    <input {...rest} type="text" inputMode={allowDecimal ? "decimal" : "numeric"} value={withCommas(raw)}
      onChange={e => { const next = toRaw(e.target.value, allowDecimal, allowNegative); if (value === undefined) setOwn(next); onValueChange?.(next); }} />
    {name && <input type="hidden" name={name} value={raw} />}
  </>;
}

// 입력값에서 숫자(필요하면 '-' 하나와 '.' 하나)만 남긴다.
function toRaw(input: string | number | null | undefined, allowDecimal: boolean, allowNegative: boolean) {
  if (input == null) return "";
  const text = String(input);
  const negative = allowNegative && text.trim().startsWith("-");
  let digits = text.replace(allowDecimal ? /[^0-9.]/g : /[^0-9]/g, "");
  if (allowDecimal) { const [whole, ...rest] = digits.split("."); digits = rest.length ? `${whole}.${rest.join("")}` : whole; }
  return (negative ? "-" : "") + digits;
}

export function withCommas(raw: string) {
  const match = raw.match(/^(-?)(\d*)(\.\d*)?$/);
  if (!match) return raw;
  return match[1] + match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (match[3] ?? "");
}
