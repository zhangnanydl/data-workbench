import {
  ArrowsLeftRight,
  CaretDown,
  ChartDonut,
  ClockCounterClockwise,
  Columns,
  Database,
  FileArrowDown,
  FileCsv,
  FileText,
  FlowArrow,
  Funnel,
  GearSix,
  Lock,
  Network,
  Rows,
  SquaresFour,
  TextAa,
  TextT,
  UsersThree,
} from "@phosphor-icons/react";

const iconMap = {
  "arrows-left-right": ArrowsLeftRight,
  columns: Columns,
  database: Database,
  "file-arrow-down": FileArrowDown,
  "file-csv": FileCsv,
  "file-text": FileText,
  funnel: Funnel,
  lock: Lock,
  network: Network,
  rows: Rows,
  "squares-four": SquaresFour,
  "text-aa": TextAa,
  "text-t": TextT,
  "users-three": UsersThree,
  flow: FlowArrow,
  history: ClockCounterClockwise,
  settings: GearSix,
  report: ChartDonut,
  down: CaretDown,
};

export function Icon({ name, size = 18, weight = "regular", ...props }) {
  const Component = iconMap[name] || SquaresFour;
  return <Component size={size} weight={weight} {...props} />;
}
