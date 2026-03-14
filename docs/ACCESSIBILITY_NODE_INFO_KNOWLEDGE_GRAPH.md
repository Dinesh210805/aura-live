# AccessibilityNodeInfo — Knowledge Graph
> Source: developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo  
> Cross-referenced against Aura's `UITreeExtractor.kt` / `UIElementData` / `format_ui_tree()`  
> Date: March 2026

---

## 1. What AccessibilityNodeInfo Is

```
AccessibilityService
       │
       ▼
  rootInActiveWindow ──► AccessibilityNodeInfo (root)
                                │
                          ┌─────┴──────┐
                      child[0]     child[1] ...
                         │               │
                     grandchildren   grandchildren
```

- Every visible View in an Android app is represented as a **node** in this tree.
- The tree is **immutable** once delivered to a service — you cannot force state onto it.
- Nodes are **recycled** (call `recycle()`) — holding them too long causes stale data.
- Custom views may NOT map 1:1 to the View hierarchy (a custom component can report itself as multiple nodes).

---

## 2. Complete Field Map

### 2A. Identity & Labels

| API Method | Key Name (sent to Python) | Type | Notes |
|---|---|---|---|
| `getText()` | `text` | String? | Visible text content |
| `getContentDescription()` | `contentDescription` | String? | TalkBack label, image alt-text |
| `getHintText()` | `hintText` | String? | Placeholder text in EditText when empty ⚠️ |
| `isShowingHintText()` | `isShowingHintText` | Boolean | TRUE = `text` field IS the hint, not real content ⚠️ |
| `getViewIdResourceName()` | `viewId` | String? | Format `"pkg:id/name"` — strip prefix for short form |
| `getClassName()` | `className` | String? | e.g. `android.widget.EditText` |
| `getPackageName()` | `packageName` | String? | App package |
| `getUniqueId()` | `uniqueId` | String? | Stable across sessions (API 33+) |
| `getContainerTitle()` | `containerTitle` | String? | Section/card title for grouped elements (API 33+) |
| `getError()` | `errorText` | String? | Validation error shown on the field |

### 2B. Geometric Position

| API Method | Key | Notes |
|---|---|---|
| `getBoundsInScreen(Rect)` | `bounds` | Screen-absolute → use this for tapping |
| `getBoundsInWindow(Rect)` | — | Window-relative; rarely needed |
| `getBoundsInParent(Rect)` | — | **Deprecated API 29** — do not use |
| `getDrawingOrder()` | `drawingOrder` | Z-order within parent; higher = drawn on top |

### 2C. Boolean Interaction Flags (What the Agent Can Do)

| API Method | Key | Currently in UIElementData? | Critical for Aura? |
|---|---|---|---|
| `isClickable()` | `isClickable` | ✅ YES | ✅ Core |
| `isLongClickable()` | `isLongClickable` | ❌ NO | ⚠️ Mid — context menus |
| `isScrollable()` | `isScrollable` | ✅ YES | ✅ Core |
| `isEditable()` | `isEditable` | ✅ YES | ✅ Core |
| `isDismissable()` | `isDismissable` | ❌ NO | ⚠️ Mid — dialogs/sheets |
| `canOpenPopup()` | `canOpenPopup` | ❌ NO | ⚠️ Mid — autocomplete/pickers |
| `isContextClickable()` | — | ❌ NO | Low |

### 2D. Boolean State Flags (Current Widget State)

| API Method | Key | Currently in UIElementData? | Critical for Aura? |
|---|---|---|---|
| `isEnabled()` | `isEnabled` | ✅ YES | ✅ Core — don't tap disabled buttons |
| `isFocused()` | `isFocused` | ✅ YES | ✅ Core — active input field |
| `isChecked()` | `isChecked` | ❌ NO | 🔴 HIGH — toggles, checkboxes, radios |
| `isCheckable()` | `isCheckable` | ❌ NO | ⚠️ Mid — reveals toggle capability |
| `isSelected()` | `isSelected` | ❌ NO | 🔴 HIGH — tabs, list selection |
| `isPassword()` | `isPassword` | ❌ NO | 🔴 HIGH — affects input + privacy |
| `isMultiLine()` | `isMultiLine` | ❌ NO | ⚠️ Mid — newline vs send key |
| `isHeading()` | `isHeading` | ❌ NO | ⚠️ Low-Mid — structural context |
| `isContentInvalid()` | `isContentInvalid` | ❌ NO | ⚠️ Mid — form validation failed |
| `isFieldRequired()` | `isFieldRequired` | ❌ NO | ⚠️ Mid — required field marker (API 29+) |
| `isAccessibilityFocused()` | — | ❌ NO | Low — TalkBack cursor |
| `isImportantForAccessibility()` | — | ❌ NO | Low |
| `isShowingHintText()` | `isShowingHintText` | ❌ NO | 🔴 HIGH — see §2A |

### 2E. Text Input Metadata

| API Method | Key | Currently in UIElementData? | Notes |
|---|---|---|---|
| `getInputType()` | `inputType` | ❌ NO | Int bitmask: email=0x21, phone=0x3, number=0x2, url=0x11 |
| `getMaxTextLength()` | `maxTextLength` | ❌ NO | -1 = no limit; agent should truncate to this |
| `getTextSelectionStart()` | — | ❌ NO | Cursor position |
| `getTextSelectionEnd()` | — | ❌ NO | Selection range |

### 2F. Collection / List / Grid Metadata

| API / Nested Class | Key | Notes |
|---|---|---|
| `getCollectionInfo()` → `CollectionInfo` | `collectionInfo` | Present on RecyclerView/ListView root |
| `CollectionInfo.getRowCount()` | `rowCount` | Total rows in list |
| `CollectionInfo.getColumnCount()` | `columnCount` | Total columns in grid |
| `CollectionInfo.getSelectionMode()` | `selectionMode` | NONE / SINGLE / MULTIPLE |
| `getCollectionItemInfo()` → `CollectionItemInfo` | `collectionItemInfo` | Present on each list item |
| `CollectionItemInfo.getRowIndex()` | `rowIndex` | 0-based row of this item |
| `CollectionItemInfo.getColumnIndex()` | `columnIndex` | 0-based column of this item |
| `CollectionItemInfo.getRowSpan()` | `rowSpan` | How many rows item spans |
| `CollectionItemInfo.getColumnSpan()` | `columnSpan` | How many columns item spans |

### 2G. Range / Progress / SeekBar Metadata

| API / Nested Class | Key | Notes |
|---|---|---|
| `getRangeInfo()` → `RangeInfo` | `rangeInfo` | Present on SeekBar, ProgressBar |
| `RangeInfo.getMin()` | `rangeMin` | Minimum value |
| `RangeInfo.getMax()` | `rangeMax` | Maximum value |
| `RangeInfo.getCurrent()` | `rangeCurrent` | Current value |
| `RangeInfo.getType()` | `rangeType` | INT / FLOAT / PERCENT |

### 2H. Available Actions (what `performAction()` accepts)

| Action Constant | Event Emitted | Notes |
|---|---|---|
| `ACTION_CLICK` | `TYPE_VIEW_CLICKED` | Standard tap |
| `ACTION_LONG_CLICK` | `TYPE_VIEW_LONG_CLICKED` | Hold gesture |
| `ACTION_SCROLL_FORWARD` | — | Scroll down/right |
| `ACTION_SCROLL_BACKWARD` | — | Scroll up/left |
| `ACTION_SCROLL_DOWN/UP/LEFT/RIGHT` | — | Directional scroll (API 23+) |
| `ACTION_SET_TEXT` | — | Type text (Bundle: `ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE`) |
| `ACTION_FOCUS` | `TYPE_VIEW_FOCUSED` | Set input focus |
| `ACTION_COPY / PASTE / CUT` | — | Clipboard ops |
| `ACTION_COLLAPSE / EXPAND` | — | Expandable containers |
| `ACTION_DISMISS` | — | Dismiss dialogs |
| `ACTION_SHOW_ON_SCREEN` | — | Scroll node into view |
| `ACTION_SET_SELECTION` | — | Move cursor (Bundle: start, end int) |
| `ACTION_SET_PROGRESS` | — | Set SeekBar value |
| `ACTION_IME_ENTER` | — | Trigger keyboard "done/go/search" action |
| `ACTION_SELECT / CLEAR_SELECTION` | — | Select/deselect node |

> **Key rule**: You cannot `performAction` on a sealed (delivered) node to change its properties.
> You can only call `performAction` to trigger UI interaction.

### 2I. Tree Navigation

| Method | Notes |
|---|---|
| `getParent()` | Navigate up |
| `getChild(index)` | Navigate down |
| `getChildCount()` | Number of children |
| `findAccessibilityNodeInfosByText(text)` | Partial match search |
| `findAccessibilityNodeInfosByViewId(id)` | Exact fully-qualified id match |
| `getTraversalAfter()` / `getTraversalBefore()` | Custom tab order |

---

## 3. Aura Gap Analysis

### 3A. Fields NOT in `UIElementData` (Kotlin) but High Value

| Field | Priority | Why it matters for Aura |
|---|---|---|
| `hintText` + `isShowingHintText` | 🔴 CRITICAL | Agent confuses hint text ("Search…") for real content. If `isShowingHintText=true`, the field is EMPTY. |
| `isChecked` | 🔴 HIGH | Toggles, checkboxes, radio buttons — agent must read current state before acting. |
| `isSelected` | 🔴 HIGH | Tab bars, chip filters, list items — agent needs to know which tab is active. |
| `isPassword` | 🔴 HIGH | Agent must not log content; also needs to know keyboard shows masked input. |
| `getError()` | 🔴 HIGH | After a failed form submission, error messages are in this field, not `text`. |
| `isContentInvalid` | ⚠️ MED | Quick flag for "previous action left field in bad state". |
| `getCollectionInfo()` | ⚠️ MED | Tells agent "this list has 42 items over N rows" — helps scroll-to decisions. |
| `getCollectionItemInfo()` | ⚠️ MED | Tells agent "this is item 3 of 42" — avoids off-by-one tap errors. |
| `getRangeInfo()` | ⚠️ MED | SeekBars — agent knows how far to drag for a target value. |
| `isMultiLine` | ⚠️ MED | Determines whether Enter = newline or submit. |
| `getInputType()` | ⚠️ MED | Agent selects correct keyboard type (email/number/phone). |
| `getMaxTextLength()` | ⚠️ MED | Agent truncates generated input to fit the field limit. |
| `isLongClickable` | ⚠️ LOW-MED | Context menus on messages, items — agent gains extra action options. |
| `isDismissable` | ⚠️ LOW-MED | Agent can classify overlays/dialogs and know to dismiss vs interact. |
| `canOpenPopup` | ⚠️ LOW-MED | Dropdown, date-picker, autocomplete — first tap opens picker, not keyboard. |
| `isHeading` | ⚠️ LOW | Structural navigation context. |
| `isFieldRequired` | ⚠️ LOW | Required form fields (API 29+). |

### 3B. Fields Already in `UIElementData` (All Good)

`text`, `contentDescription`, `bounds` (full BoundsData with center), `className`, `isClickable` (with parent inheritance), `isScrollable`, `isEditable`, `isEnabled`, `isFocused`, `actions` (list of performable action names), `packageName`, `viewId`

### 3C. Fields in `format_ui_tree()` but NOT in `UIElementData`  

> These are Python-side best-effort fields read from raw dicts — only as good as what Kotlin sends.

`hint` (partial coverage), `isChecked`, `isSelected`, `isPassword`, `focused` — these exist in `format_ui_tree()` but will be empty/default unless Kotlin sends them.

---

## 4. Recommended Additions to `UIElementData` (Kotlin)

```kotlin
data class UIElementData(
    // --- existing fields ---
    val text: String?,
    val contentDescription: String?,
    val bounds: BoundsData,
    val className: String?,
    val isClickable: Boolean,
    val isScrollable: Boolean,
    val isEditable: Boolean,
    val isEnabled: Boolean,
    val isFocused: Boolean,
    val actions: List<String>,
    val packageName: String?,
    val viewId: String?,

    // --- ADD THESE ---
    val hintText: String? = null,          // placeholder when field empty
    val isShowingHintText: Boolean = false, // true = text IS the hint, field is empty
    val isChecked: Boolean = false,        // toggle/checkbox/radio state
    val isCheckable: Boolean = false,      // can be checked/unchecked
    val isSelected: Boolean = false,       // tab/chip/list selection state
    val isPassword: Boolean = false,       // password masking active
    val isLongClickable: Boolean = false,  // context menu available
    val isMultiLine: Boolean = false,      // multi-line text input
    val isDismissable: Boolean = false,    // dialog/sheet can be dismissed
    val canOpenPopup: Boolean = false,     // tap opens picker/dropdown
    val isContentInvalid: Boolean = false, // validation error state
    val errorText: String? = null,         // error message text
    val inputType: Int = 0,               // keyboard type bitmask
    val maxTextLength: Int = -1,          // max chars (-1 = unlimited)
    val collectionRowCount: Int = -1,     // list total rows
    val collectionColumnCount: Int = -1,  // grid total columns
    val collectionItemRow: Int = -1,      // item's row in list
    val collectionItemColumn: Int = -1,   // item's column in grid
    val rangeMin: Float = 0f,             // seekbar min
    val rangeMax: Float = 0f,             // seekbar max
    val rangeCurrent: Float = 0f,         // seekbar current value
)
```

### Extraction snippet for `UITreeExtractor.kt`

```kotlin
// In extractUIElements(), replace element construction block:

val hintText = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
    node.hintText?.toString() else null

val isShowingHintText = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
    node.isShowingHintText else false

val colInfo = node.collectionInfo
val itemInfo = node.collectionItemInfo
val rangeInfo = node.rangeInfo

val element = UIElementData(
    // ... existing fields ...
    hintText = hintText,
    isShowingHintText = isShowingHintText,
    isChecked = node.isChecked,
    isCheckable = node.isCheckable,
    isSelected = node.isSelected,
    isPassword = node.isPassword,
    isLongClickable = node.isLongClickable,
    isMultiLine = node.isMultiLine,
    isDismissable = node.isDismissable,
    canOpenPopup = node.canOpenPopup(),
    isContentInvalid = node.isContentInvalid,
    errorText = node.error?.toString(),
    inputType = node.inputType,
    maxTextLength = node.maxTextLength,
    collectionRowCount = colInfo?.rowCount ?: -1,
    collectionColumnCount = colInfo?.columnCount ?: -1,
    collectionItemRow = itemInfo?.rowIndex ?: -1,
    collectionItemColumn = itemInfo?.columnIndex ?: -1,
    rangeMin = rangeInfo?.min ?: 0f,
    rangeMax = rangeInfo?.max ?: 0f,
    rangeCurrent = rangeInfo?.current ?: 0f,
)
```

---

## 5. Impact on Python Backend

### `format_ui_tree()` in `utils/ui_element_finder.py`

Once Kotlin sends the new fields, `format_ui_tree()` can surface them. Suggested additions:

```
[3] EditText | hint='Email address' | id=email_input | bounds=[100,200→980,280] | CLICK | EDIT | FOCUSED | EMPTY(hint) | EMAIL_INPUT | pkg=gmail
[7] CheckBox | 'Remember me' | id=cb_remember | bounds=[50,400→400,460] | CLICK | CHECKED | pkg=gmail
[9] SeekBar | '' | id=volume_seek | bounds=[50,600→1030,660] | RANGE:0→100@67 | pkg=settings
[12] Button | 'Submit' | id=btn_submit | bounds=[200,800→880,900] | CLICK | DISABLED | ERROR_STATE | pkg=gmail
```

### Prompt Impact (Perceiver / Reactive Step Gen)

With these fields, VLM agents can:
- Know a field is **empty** (not just showing hint text as if it has content)
- Know a **toggle is already ON** before tapping it again
- Detect **form validation errors** after a submit attempt
- Know the **active tab** in a bottom nav bar
- Know a **button is disabled** and seek an alternative path
- Read **SeekBar position** and compute the correct drag direction/distance

---

## 6. Key Gotchas & Rules

| Rule | Detail |
|---|---|
| **`getBoundsInParent` deprecated** | Use `getBoundsInScreen` only (API 29+) |
| **Node recycling** | Always `node.recycle()` after traversal — stale nodes cause crashes |
| **Sealed nodes are immutable** | You cannot set properties on a node delivered to your service |
| **`findAccessibilityNodeInfosByText` = substring match** | Returns ALL nodes containing the string anywhere in text |
| **Clickable parent inheritance** | A TextView inside a clickable LinearLayout reports `isClickable=false` — must check parent (already handled in Aura's `UITreeExtractor`) |
| **`isShowingHintText` guard** | When `isShowingHintText=true`, the `text` value is the placeholder, NOT real input — treat the field as empty |
| **`inputType` bitmask** | Combine with `TYPE_MASK_CLASS` (0xF): result 1=text, 2=number, 3=phone, 4=datetime; combine with `TYPE_MASK_VARIATION` for email (0x20), URI (0x10), password (0x80) |
| **`performAction(ACTION_SCROLL_FORWARD)` on root** | Root node is rarely scrollable — must find the scrollable child first |
| **`isEditable` vs `inputType`** | Some custom inputs are `isEditable=false` but do respond to tap+keyboard; `inputType != 0` is a stronger indicator |
| **Stale tree after action** | After `performAction`, re-fetch the UI tree — node state is not updated in-place |

---

## 7. Relationship Graph (Simplified)

```
AccessibilityNodeInfo
├── IDENTITY
│   ├── className ──────────────── widget type
│   ├── viewId ─────────────────── stable resource name
│   ├── packageName ─────────────── owning app
│   ├── text ────────────────────── visible label
│   ├── contentDescription ─────── TalkBack label  
│   ├── hintText ────────────────── placeholder [MISSING in Aura]
│   └── errorText ───────────────── validation error [MISSING in Aura]
│
├── GEOMETRY
│   ├── getBoundsInScreen ──────── tap coordinates (✅ in Aura)
│   └── drawingOrder ────────────── z-order
│
├── INTERACTION FLAGS (can agent do this?)
│   ├── isClickable ────────────── ✅ captured
│   ├── isScrollable ───────────── ✅ captured
│   ├── isEditable ─────────────── ✅ captured
│   ├── isLongClickable ──────────  ❌ MISSING
│   ├── isDismissable ────────────  ❌ MISSING
│   └── canOpenPopup ─────────────  ❌ MISSING
│
├── STATE FLAGS (current widget state)
│   ├── isEnabled ──────────────── ✅ captured
│   ├── isFocused ──────────────── ✅ captured
│   ├── isChecked ───────────────── ❌ MISSING 🔴
│   ├── isSelected ──────────────── ❌ MISSING 🔴
│   ├── isPassword ──────────────── ❌ MISSING 🔴
│   ├── isShowingHintText ─────────  ❌ MISSING 🔴
│   ├── isMultiLine ─────────────── ❌ MISSING
│   └── isContentInvalid ───────── ❌ MISSING
│
├── ACTIONS (what performAction accepts)
│   ├── ACTION_CLICK ───────────── ✅ surfaced in actions[]
│   ├── ACTION_LONG_CLICK ─────── ✅ surfaced in actions[]
│   ├── ACTION_SCROLL_FORWARD ─── ✅ surfaced in actions[]
│   ├── ACTION_SET_TEXT ────────── ✅ surfaced in actions[]
│   ├── ACTION_IME_ENTER ──────── ❌ not surfaced
│   ├── ACTION_DISMISS ─────────── ❌ not surfaced
│   ├── ACTION_EXPAND/COLLAPSE ─── ❌ not surfaced
│   └── ACTION_SET_PROGRESS ───── ❌ not surfaced
│
└── STRUCTURED METADATA (nested classes)
    ├── CollectionInfo ───────────── ❌ MISSING (list/grid size)
    ├── CollectionItemInfo ─────────  ❌ MISSING (item position)
    └── RangeInfo ────────────────── ❌ MISSING (seekbar values)
```

---

## 8. What to Implement Next (Priority Order)

| # | Change | Where | Impact |
|---|---|---|---|
| 1 | Add `hintText`, `isShowingHintText`, `isChecked`, `isSelected`, `isPassword`, `errorText`, `isContentInvalid` to `UIElementData` + `UITreeExtractor` | Kotlin | 🔴 Fixes agent confusion on empty inputs, toggles, form errors |
| 2 | Update `format_ui_tree()` to surface new flags — `EMPTY(hint)`, `CHECKED`, `SELECTED`, `PWD`, `INVALID` | Python `utils/ui_element_finder.py` | 🔴 VLM sees richer context |
| 3 | Add `isMultiLine`, `inputType`, `maxTextLength` to extraction | Kotlin | ⚠️ Prevents double-Enter, keyboard type mismatch |
| 4 | Add `CollectionInfo` + `CollectionItemInfo` to extraction | Kotlin | ⚠️ Better list/grid navigation |
| 5 | Add `isDismissable`, `canOpenPopup`, `isLongClickable` | Kotlin | ⚠️ New action paths for agent |
| 6 | Add `RangeInfo` fields | Kotlin | ⚠️ SeekBar control |
| 7 | Surface `ACTION_IME_ENTER`, `ACTION_DISMISS`, `ACTION_EXPAND` in actions list | Kotlin | ⚠️ Agent discovers more actions |
