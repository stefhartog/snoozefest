((LitElement) => {
	const html = LitElement.prototype.html;
	const css = LitElement.prototype.css;
	const version = '0.4.2-custom';

	/*
	Public options

	Required:
	- entity | display_entity
	  - entity: HA entity to write to / bind directly
	  - display_entity: entity to render when different from write target

	Base behavior:
	- read_only: true | false
	- autosave: true | false
	- at_right: true | false
	- tap_sets_timer_id: helper entity id string
	- hold_dismisses: true | false
	- mqtt_prefix: string, defaults to snoozefest
	- title: free text string
	- pending_write_ms: number in ms

	Visible segments:
	- show_days: true | false
	- show_seconds: true | false
	- days_placeholder, hour_placeholder, minute_placeholder, second_placeholder: string
	- separator_mode: colon | units | none
	- separator: string, used when separator_mode is none/custom-style display
	- unit_suffix_days, unit_suffix_hours, unit_suffix_minutes, unit_suffix_seconds: string

	Main layout and style:
	- content_justify: flex-start | center | flex-end | space-between | space-around | space-evenly
	- content_align: flex-start | center | flex-end | stretch
	- color: CSS color
	- font_size: CSS size or number-like string
	- input_width: CSS size
	- input_padding: CSS padding value
	- input_border_radius: CSS radius
	- input_background: CSS color/background
	- card_background: CSS color/background
	- card_border: true | false
	- padding: CSS padding shorthand
	- padding_top_bottom, padding_left_right: CSS size
	- padding_top, padding_bottom, padding_left, padding_right: CSS size
	- content_offset_x, content_offset_y: CSS size, positive or negative

	Steppers:
	- show_steppers: true | false
	- stepper_size: CSS size, visual arrow size
	- stepper_hit_height: CSS size, clickable strip height
	- stepper_color: CSS color
	- stepper_opacity: 0..1 string/number
	- stepper_active_opacity: 0..1 string/number
	- stepper_input_pad_y: CSS size, reserves room above/below input
	- stepper_offset: CSS size, distance from input box
	- stepper_stroke: CSS size, arrow line thickness

	Status colors:
	- status_entity: explicit entity id string
	- status_color_target: none | input | card | both
	- status_color_default, status_color_inactive, status_color_active: CSS color
	- status_color_snoozed, status_color_paused, status_color_ringing: CSS color
	- status_opacity_default, status_opacity_inactive, status_opacity_active: 0..1 string/number
	- status_opacity_snoozed, status_opacity_paused, status_opacity_ringing: 0..1 string/number

	Secondary content:
	- secondary_mode: none | status | remaining | weekday | weekday_smart | smart_weekday | label | entity
	- secondary_variant: text | icon
	- secondary_text: free text string
	- secondary_entity: entity id string
	- secondary_anchor: content | card
	- secondary_position:
	  - content anchor: above | below | left | right | top | bottom | topleft | topright | bottomleft | bottomright | topcenter | bottomcenter | centerleft | centerright
	  - card anchor: center | top | bottom | left | right | topleft | topright | bottomleft | bottomright | centerleft | centerright | topcenter | bottomcenter
	- secondary_align: left | center | right
	- secondary_gap: CSS size
	- secondary_font_size: CSS size
	- secondary_color: CSS color
	- secondary_opacity: 0..1 string/number
	- secondary_font_weight: normal | bold | 100..900
	- secondary_padding: CSS padding value
	- secondary_offset_x, secondary_offset_y: CSS size, positive or negative
	- secondary_z_index: integer/number
	- secondary_pointer_events: none | auto
	- secondary_icon: mdi:* icon name
	- secondary_icon_state_entity: entity id string
	- secondary_icon_on, secondary_icon_off: mdi:* icon name
	- secondary_icon_size: CSS size
	- secondary_icon_on_color, secondary_icon_off_color: CSS color
	- secondary_icon_on_opacity, secondary_icon_off_opacity: 0..1 string/number
	- secondary_icon_background: CSS color/background
	- secondary_icon_border_radius: CSS radius
	- secondary_icon_padding: CSS padding value
	- secondary_click_action: none | tap_select | dismiss | remove | service | toggle_switch
	- secondary_click_service: domain.service string
	- secondary_click_entity: entity id string
	- secondary_click_data: object
	- secondary_click_stop_propagation: true | false
	- secondary_aria_label: free text string

	Secondary button:
	- secondary_button: true | false
	- secondary_button_anchor: content | card
	- secondary_button_position:
	  - content anchor: above | below | left | right | top | bottom | topleft | topright | bottomleft | bottomright | topcenter | bottomcenter | centerleft | centerright
	  - card anchor: center | top | bottom | left | right | topleft | topright | bottomleft | bottomright | centerleft | centerright | topcenter | bottomcenter
	- secondary_button_align: left | center | right
	- secondary_button_offset_x, secondary_button_offset_y: CSS size, positive or negative
	- secondary_button_z_index: integer/number
	- secondary_button_pointer_events: none | auto
	- secondary_button_icon: mdi:* icon name
	- secondary_button_icon_state_entity: entity id string
	- secondary_button_icon_on, secondary_button_icon_off: mdi:* icon name
	- secondary_button_icon_size: CSS size
	- secondary_button_icon_on_color, secondary_button_icon_off_color: CSS color
	- secondary_button_icon_on_opacity, secondary_button_icon_off_opacity: 0..1 string/number
	- secondary_button_icon_background: CSS color/background
	- secondary_button_icon_border_radius: CSS radius
	- secondary_button_icon_padding: CSS padding value
	- secondary_button_click_action: none | tap_select | dismiss | remove | service | toggle_switch
	- secondary_button_click_service: domain.service string
	- secondary_button_click_entity: entity id string
	- secondary_button_click_data: object
	- secondary_button_click_stop_propagation: true | false
	- secondary_button_aria_label: free text string
	*/

	const TIMER_REMAINING_RE = /^sensor\..+_timer_\d+_remaining(?:_friendly)?$/;
	const ALARM_REMAINING_RE = /^sensor\..+_alarm_\d+_remaining(?:_friendly)?$/;
	const TIMER_DURATION_RE = /^(?:text|input_text)\..+_timer_\d+_duration$/;
	const ALARM_TIME_RE = /^(?:text|input_text)\..+_alarm_\d+_time$/;
	const TIMER_VALUE_ENTITY_RE = /^(text|input_text|sensor)\..+_timer_\d+_(?:duration|remaining(?:_friendly)?)$/;
	const ENTITY_BASE_RE = /^sensor\.(.+_(?:timer|alarm)_\d+)_remaining(?:_friendly)?$/;
	const TIMER_DURATION_BASE_RE = /^(?:text|input_text)\.(.+_timer_\d+)_duration$/;
	const ALARM_TIME_BASE_RE = /^(?:text|input_text)\.(.+_alarm_\d+)_time$/;
	const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
	const CARD_ANCHOR_POSITIONS = new Set([
		'center', 'top', 'bottom', 'left', 'right', 'topleft', 'topright',
		'bottomleft', 'bottomright', 'centerleft', 'centerright', 'topcenter', 'bottomcenter',
	]);
	const CONTENT_ANCHOR_POSITIONS = new Set([
		'above', 'below', 'left', 'right', 'top', 'bottom', 'topleft', 'topright',
		'bottomleft', 'bottomright', 'topcenter', 'bottomcenter', 'centerleft', 'centerright',
	]);
	const SEGMENT_DEFINITIONS = {
		days: { prop: 'daysText', max: 99, placeholderKey: 'days_placeholder', unitKey: 'unit_suffix_days', fallbackPlaceholder: 'DD' },
		hours: { prop: 'hourText', max: 23, placeholderKey: 'hour_placeholder', unitKey: 'unit_suffix_hours', fallbackPlaceholder: 'HH' },
		minutes: { prop: 'minuteText', max: 59, placeholderKey: 'minute_placeholder', unitKey: 'unit_suffix_minutes', fallbackPlaceholder: 'MM' },
		seconds: { prop: 'secondText', max: 59, placeholderKey: 'second_placeholder', unitKey: 'unit_suffix_seconds', fallbackPlaceholder: 'SS' },
	};

	function stringValue(value, fallback = null) {
		return value != null ? String(value) : fallback;
	}

	function lowerString(value, fallback = '') {
		return value != null ? String(value).toLowerCase() : fallback;
	}

	function objectValue(value) {
		return value != null && typeof value === 'object' ? value : null;
	}

	class SnoozefestEntityCard extends LitElement {
		constructor() {
			super();
			this._onKeydown = this._onKeydown.bind(this);
			this._onCommit = this._onCommit.bind(this);
			this._onInputFocus = this._onInputFocus.bind(this);
			this._onStepperPointerDown = this._onStepperPointerDown.bind(this);
			this._onCardPointerDown = this._onCardPointerDown.bind(this);
			this._onCardPointerUp = this._onCardPointerUp.bind(this);
			this._onCardPointerCancel = this._onCardPointerCancel.bind(this);
			this._pendingValue = null;
			this._pendingPrevValue = null;
			this._pendingSince = 0;
			this._pendingUntil = 0;
			this._holdTimer = null;
			this._holdFired = false;
		}

		static get properties() {
			return {
				_hass: {},
				config: {},
				stateObj: {},
				daysText: {},
				hourText: {},
				minuteText: {},
				secondText: {},
			};
		}

		static get styles() {
			return css`
				.wrapper {
					display: flex;
					width: 100%;
					justify-content: var(--stpc-justify-content, flex-start);
					align-items: var(--stpc-align-items, center);
					gap: var(--stpc-gap, 6px);
				}
				.segment {
					position: relative;
					display: inline-flex;
					align-items: center;
				}
				.input-wrap {
					display: inline-flex;
					align-items: center;
					justify-content: center;
					background: var(--stpc-input-background, transparent);
					border-radius: var(--stpc-input-border-radius, 0);
					padding: var(--stpc-input-padding, 0);
				}
				.input-wrap.with-steppers {
					padding-top: var(--stpc-stepper-input-pad-y, 0.65em);
					padding-bottom: var(--stpc-stepper-input-pad-y, 0.65em);
				}
				.input {
					width: var(--stpc-input-width, 2.4em);
					text-align: center;
					border: none;
					outline: none;
					background: transparent;
					color: inherit;
					font: inherit;
					line-height: inherit;
					padding: 0;
					margin: 0;
				}
				.input[readonly] {
					user-select: none;
					-webkit-user-select: none;
					caret-color: transparent;
					cursor: default;
					pointer-events: none;
				}
				.stepper-btn {
					position: absolute;
					left: 0;
					right: 0;
					display: flex;
					align-items: center;
					justify-content: center;
					border: 0;
					background: transparent;
					padding: 0;
					margin: 0;
					line-height: 1;
					cursor: pointer;
					touch-action: manipulation;
					color: var(--stpc-stepper-color, currentColor);
					opacity: var(--stpc-stepper-opacity, 0.28);
				}
				.stepper-btn:hover,
				.stepper-btn:focus-visible {
					opacity: var(--stpc-stepper-active-opacity, 0.75);
				}
				.stepper-btn.up {
					top: calc(-1 * var(--stpc-stepper-offset, 0.1em));
					height: var(--stpc-stepper-hit-height, 1em);
				}
				.stepper-btn.down {
					bottom: calc(-1 * var(--stpc-stepper-offset, 0.1em));
					height: var(--stpc-stepper-hit-height, 1em);
				}
				.stepper-glyph {
					display: inline-block;
					width: var(--stpc-stepper-size, 0.5em);
					height: var(--stpc-stepper-size, 0.5em);
					box-sizing: border-box;
					border-right: var(--stpc-stepper-stroke, 0.11em) solid currentColor;
					border-bottom: var(--stpc-stepper-stroke, 0.11em) solid currentColor;
					pointer-events: none;
				}
				.stepper-btn.up .stepper-glyph {
					transform: rotate(-135deg);
				}
				.stepper-btn.down .stepper-glyph {
					transform: rotate(45deg);
				}
				.separator {
					user-select: none;
					opacity: 0.8;
				}
				.content {
					position: relative;
					display: flex;
					width: 100%;
					gap: var(--stpc-secondary-gap, 6px);
				}
				.content.anchor-card {
					display: block;
				}
				.main {
					width: 100%;
					transform: translate(var(--stpc-main-offset-x, 0), var(--stpc-main-offset-y, 0));
				}
				.content.anchor-content.pos-left .main,
				.content.anchor-content.pos-right .main {
					flex: 1 1 auto;
					min-width: 0;
				}
				.content.pos-below,
				.content.pos-above {
					flex-direction: column;
				}
				.content.pos-left,
				.content.pos-right {
					flex-direction: row;
					align-items: center;
				}
				.secondary {
					line-height: 1.2;
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
					min-width: 0;
					max-width: 100%;
				}
				.secondary.icon {
					display: inline-flex;
					align-items: center;
					justify-content: center;
					white-space: normal;
					overflow: visible;
				}
				.secondary.icon ha-icon {
					width: var(--stpc-secondary-icon-size, 1em);
					height: var(--stpc-secondary-icon-size, 1em);
					--mdc-icon-size: var(--stpc-secondary-icon-size, 1em);
				}
				.secondary-btn {
					appearance: none;
					border: 0;
					background: transparent;
					color: inherit;
					font: inherit;
					line-height: 0;
					padding: 0;
					margin: 0;
					cursor: pointer;
					display: inline-flex;
					align-items: center;
					justify-content: center;
					vertical-align: middle;
				}
				.secondary-btn.icon ha-icon {
					display: block;
					width: var(--stpc-secondary-btn-icon-size, 1em);
					height: var(--stpc-secondary-btn-icon-size, 1em);
					--mdc-icon-size: var(--stpc-secondary-btn-icon-size, 1em);
				}
				.secondary.anchor-card {
					position: absolute;
				}
				.missing-entity {
					color: var(--secondary-text-color);
					font-size: 0.85em;
				}
				ha-card,
				ha-card * {
					box-sizing: border-box;
				}
			`;
		}

		setConfig(config) {
			this.config = this._buildConfig(config);
			this.daysText = '';
			this.hourText = '';
			this.minuteText = '';
			this.secondText = '';
		}

		_buildConfig(config) {
			this._validateConfig(config);
			const readOnly = config.read_only === true;
			const writeEntity = config.entity ? String(config.entity) : null;
			const displayEntity = config.display_entity ? String(config.display_entity) : writeEntity;
			return {
				...this._buildBaseConfig(config, writeEntity, displayEntity, readOnly),
				...this._buildStepperConfig(config),
				...this._buildStatusConfig(config),
				...this._buildStyleConfig(config),
				...this._buildSecondaryConfig(config),
				...this._buildSecondaryButtonConfig(config),
			};
		}

		_validateConfig(config) {
			if (!config || (!config.entity && !config.display_entity)) {
				throw new Error('Please define entity or display_entity for this card.');
			}

			const writeEntity = config.entity ? String(config.entity) : null;
			const displayEntity = config.display_entity ? String(config.display_entity) : writeEntity;
			if (!displayEntity) {
				throw new Error('A display entity could not be resolved.');
			}

			const writeDomain = writeEntity ? writeEntity.split('.')[0] : null;
			const displayDomain = displayEntity.split('.')[0];
			if (writeEntity && writeDomain !== 'text' && writeDomain !== 'input_text') {
				throw new Error('entity must be text or input_text.');
			}
			if (displayDomain !== 'text' && displayDomain !== 'input_text' && displayDomain !== 'sensor') {
				throw new Error('display_entity must be text, input_text, or sensor.');
			}
		}

		_buildBaseConfig(config, writeEntity, displayEntity, readOnly) {
			return {
				entity: writeEntity,
				display_entity: displayEntity,
				status_entity: stringValue(config.status_entity),
				status_color_target: lowerString(config.status_color_target, 'input') || 'input',
				tap_sets_timer_id: stringValue(config.tap_sets_timer_id),
				hold_dismisses: config.hold_dismisses === true,
				mqtt_prefix: this._resolveMqttPrefix(config),
				read_only: readOnly,
				title: config.title,
				autosave: readOnly ? false : (config.autosave !== false),
				content_justify: this._normalizeFlexPosition(config.content_justify || config.justify || 'left', 'horizontal'),
				content_align: this._normalizeFlexPosition(config.content_align || config.align || 'center', 'vertical'),
				show_days: config.show_days === true,
				show_seconds: config.show_seconds === true,
				days_placeholder: config.days_placeholder || '--',
				hour_placeholder: config.hour_placeholder || '--',
				minute_placeholder: config.minute_placeholder || '--',
				second_placeholder: config.second_placeholder || '--',
				separator_mode: config.separator_mode === 'units' ? 'units' : 'colon',
				separator: config.separator || ':',
				unit_suffix_days: config.unit_suffix_days || 'd',
				unit_suffix_hours: config.unit_suffix_hours || 'h',
				unit_suffix_minutes: config.unit_suffix_minutes || 'm',
				unit_suffix_seconds: config.unit_suffix_seconds || 's',
				suffix_font_size: stringValue(config.suffix_font_size),
				suffix_color: stringValue(config.suffix_color),
				suffix_padding: stringValue(config.suffix_padding),
				suffix_opacity: stringValue(config.suffix_opacity),
				pending_write_ms: config.pending_write_ms != null ? parseInt(config.pending_write_ms, 10) : 700,
				pending_stale_ms: config.pending_stale_ms != null ? parseInt(config.pending_stale_ms, 10) : 3000,
			};
		}

		_buildStepperConfig(config) {
			return {
				show_steppers: config.show_steppers === true,
				stepper_wrap: config.stepper_wrap !== false,
				stepper_size: stringValue(config.stepper_size),
				stepper_hit_height: stringValue(config.stepper_hit_height),
				stepper_color: stringValue(config.stepper_color),
				stepper_opacity: stringValue(config.stepper_opacity),
				stepper_active_opacity: stringValue(config.stepper_active_opacity),
				stepper_input_pad_y: stringValue(config.stepper_input_pad_y),
				stepper_offset: stringValue(config.stepper_offset),
				stepper_stroke: stringValue(config.stepper_stroke),
			};
		}

		_buildStatusConfig(config) {
			return {
				input_background: stringValue(config.input_background),
				status_color_default: stringValue(config.status_color_default),
				status_color_inactive: stringValue(config.status_color_inactive),
				status_color_active: stringValue(config.status_color_active),
				status_color_snoozed: stringValue(config.status_color_snoozed),
				status_color_paused: stringValue(config.status_color_paused),
				status_color_ringing: stringValue(config.status_color_ringing),
				status_opacity_default: stringValue(config.status_opacity_default),
				status_opacity_inactive: stringValue(config.status_opacity_inactive),
				status_opacity_active: stringValue(config.status_opacity_active),
				status_opacity_snoozed: stringValue(config.status_opacity_snoozed),
				status_opacity_paused: stringValue(config.status_opacity_paused),
				status_opacity_ringing: stringValue(config.status_opacity_ringing),
			};
		}

		_buildStyleConfig(config) {
			return {
				input_padding: stringValue(config.input_padding),
				input_border_radius: stringValue(config.input_border_radius),
				card_border: config.card_border !== undefined ? config.card_border : null,
				card_background: stringValue(config.card_background),
				color: stringValue(config.color),
				font_size: config.font_size != null ? parseFloat(config.font_size) : null,
				padding: stringValue(config.padding),
				padding_left_right: stringValue(config.padding_left_right),
				padding_top_bottom: stringValue(config.padding_top_bottom),
				padding_top: stringValue(config.padding_top),
				padding_bottom: stringValue(config.padding_bottom),
				padding_left: stringValue(config.padding_left),
				padding_right: stringValue(config.padding_right),
				content_offset_x: stringValue(config.content_offset_x),
				content_offset_y: stringValue(config.content_offset_y),
				input_width: stringValue(config.input_width),
			};
		}

		_buildSecondaryConfig(config) {
			return {
				secondary_mode: lowerString(config.secondary_mode, 'none') || 'none',
				secondary_variant: lowerString(config.secondary_variant, 'text') || 'text',
				secondary_text: stringValue(config.secondary_text, '') || '',
				secondary_entity: stringValue(config.secondary_entity),
				secondary_icon: stringValue(config.secondary_icon, 'mdi:information-outline') || 'mdi:information-outline',
				secondary_icon_state_entity: stringValue(config.secondary_icon_state_entity),
				secondary_icon_on: stringValue(config.secondary_icon_on),
				secondary_icon_off: stringValue(config.secondary_icon_off),
				secondary_icon_size: stringValue(config.secondary_icon_size),
				secondary_icon_on_color: stringValue(config.secondary_icon_on_color),
				secondary_icon_off_color: stringValue(config.secondary_icon_off_color),
				secondary_icon_on_opacity: stringValue(config.secondary_icon_on_opacity),
				secondary_icon_off_opacity: stringValue(config.secondary_icon_off_opacity),
				secondary_icon_background: stringValue(config.secondary_icon_background),
				secondary_icon_border_radius: stringValue(config.secondary_icon_border_radius),
				secondary_icon_padding: stringValue(config.secondary_icon_padding),
				secondary_anchor: lowerString(config.secondary_anchor, 'content') || 'content',
				secondary_position: lowerString(config.secondary_position, 'below') || 'below',
				secondary_align: lowerString(config.secondary_align, null),
				secondary_gap: stringValue(config.secondary_gap),
				secondary_font_size: stringValue(config.secondary_font_size),
				secondary_color: stringValue(config.secondary_color),
				secondary_opacity: stringValue(config.secondary_opacity),
				secondary_font_weight: stringValue(config.secondary_font_weight),
				secondary_padding: stringValue(config.secondary_padding),
				secondary_offset_x: stringValue(config.secondary_offset_x),
				secondary_offset_y: stringValue(config.secondary_offset_y),
				secondary_z_index: stringValue(config.secondary_z_index),
				secondary_pointer_events: stringValue(config.secondary_pointer_events, 'none') || 'none',
				secondary_click_action: lowerString(config.secondary_click_action, 'none') || 'none',
				secondary_click_service: stringValue(config.secondary_click_service),
				secondary_click_entity: stringValue(config.secondary_click_entity),
				secondary_click_data: objectValue(config.secondary_click_data),
				secondary_click_stop_propagation: config.secondary_click_stop_propagation !== false,
				secondary_aria_label: stringValue(config.secondary_aria_label),
			};
		}

		_buildSecondaryButtonConfig(config) {
			return {
				secondary_button: config.secondary_button === true,
				secondary_button_icon: stringValue(config.secondary_button_icon, 'mdi:dots-horizontal') || 'mdi:dots-horizontal',
				secondary_button_icon_state_entity: stringValue(config.secondary_button_icon_state_entity),
				secondary_button_icon_on: stringValue(config.secondary_button_icon_on),
				secondary_button_icon_off: stringValue(config.secondary_button_icon_off),
				secondary_button_icon_size: stringValue(config.secondary_button_icon_size),
				secondary_button_icon_on_color: stringValue(config.secondary_button_icon_on_color),
				secondary_button_icon_off_color: stringValue(config.secondary_button_icon_off_color),
				secondary_button_icon_on_opacity: stringValue(config.secondary_button_icon_on_opacity),
				secondary_button_icon_off_opacity: stringValue(config.secondary_button_icon_off_opacity),
				secondary_button_icon_background: stringValue(config.secondary_button_icon_background),
				secondary_button_icon_border_radius: stringValue(config.secondary_button_icon_border_radius),
				secondary_button_icon_padding: stringValue(config.secondary_button_icon_padding),
				secondary_button_anchor: lowerString(config.secondary_button_anchor, null),
				secondary_button_position: lowerString(config.secondary_button_position, null),
				secondary_button_align: lowerString(config.secondary_button_align, null),
				secondary_button_offset_x: stringValue(config.secondary_button_offset_x),
				secondary_button_offset_y: stringValue(config.secondary_button_offset_y),
				secondary_button_z_index: stringValue(config.secondary_button_z_index),
				secondary_button_pointer_events: stringValue(config.secondary_button_pointer_events),
				secondary_button_click_action: lowerString(config.secondary_button_click_action, 'none') || 'none',
				secondary_button_click_service: stringValue(config.secondary_button_click_service),
				secondary_button_click_entity: stringValue(config.secondary_button_click_entity),
				secondary_button_click_data: objectValue(config.secondary_button_click_data),
				secondary_button_click_stop_propagation: config.secondary_button_click_stop_propagation !== false,
				secondary_button_aria_label: stringValue(config.secondary_button_aria_label),
			};
		}

		_resolveMqttPrefix(config) {
			const configured = stringValue(config.mqtt_prefix, '')?.trim();
			const globalPrefix = window.SNOOZEFEST_PREFIX ? String(window.SNOOZEFEST_PREFIX).trim() : '';
			return configured || globalPrefix || 'snoozefest';
		}

		set hass(hass) {
			this._hass = hass;
			if (!hass || !this.config) {
				return;
			}

			const resolvedDisplayEntity = this._resolveReadOnlyDisplayEntity();
			this.stateObj = hass.states[resolvedDisplayEntity] || null;
			if (!this.stateObj) {
				return;
			}
			this._syncFromState();
		}

		_resolveReadOnlyDisplayEntity() {
			return this._resolveEntityContext().resolvedDisplayEntity;
		}

		_resolveEntityContext(displayEntity = this.config?.display_entity) {
			const rawDisplayEntity = String(displayEntity || '');
			const selector = String(this.config?.tap_sets_timer_id || '');
			let base = null;
			let kind = null;
			let id = null;

			const baseMatch = this._matchDisplayEntityBase(rawDisplayEntity);
			if (baseMatch) {
				base = baseMatch.base;
				kind = baseMatch.kind;
				id = baseMatch.id;
			}

			if (!base) {
				kind = this._deriveSelectedEntityKind(selector);
				id = this._deriveSelectedEntityId(selector);
				if (kind && id) {
					base = `${this._getMqttPrefix()}_${kind}_${id}`;
				}
			}

			if (base) {
				const baseKindMatch = base.match(/_(timer|alarm)_\d+$/);
				const baseIdMatch = base.match(/_(?:timer|alarm)_(\d+)$/);
				kind = kind || (baseKindMatch ? baseKindMatch[1] : null);
				id = id || (baseIdMatch ? baseIdMatch[1] : null);
			}

			const resolvedDisplayEntity = this._resolveReadOnlyDisplayEntityFromContext({
				displayEntity: rawDisplayEntity,
				base,
				kind,
			});
			const statusEntity = this._resolveStatusEntity(rawDisplayEntity);

			return {
				displayEntity: rawDisplayEntity,
				resolvedDisplayEntity,
				base,
				kind,
				id,
				writeEntity: this.config?.entity || null,
				switchEntity: base ? `switch.${base}` : null,
				statusEntity,
				dismissButtonEntity: base ? `button.${base}_dismiss` : null,
				removeButtonEntity: base ? `button.${base}_remove` : null,
				nextDayEntity: base ? `sensor.${base}_next_day` : null,
				remainingEntity: base ? `sensor.${base}_remaining` : null,
				friendlyRemainingEntity: base ? `sensor.${base}_remaining_friendly` : null,
				weekdaySwitchEntities: kind === 'alarm' && base
					? Array.from({ length: 7 }, (_, wd) => `switch.${base}_weekday_${wd}`)
					: [],
			};
		}

		_matchDisplayEntityBase(displayEntity) {
			const match = String(displayEntity || '').match(ENTITY_BASE_RE) || String(displayEntity || '').match(TIMER_DURATION_BASE_RE) || String(displayEntity || '').match(ALARM_TIME_BASE_RE);
			if (!match) {
				return null;
			}
			const base = match[1];
			const kindMatch = base.match(/_(timer|alarm)_\d+$/);
			const idMatch = base.match(/_(?:timer|alarm)_(\d+)$/);
			return {
				base,
				kind: kindMatch ? kindMatch[1] : null,
				id: idMatch ? idMatch[1] : null,
			};
		}

		_resolveReadOnlyDisplayEntityFromContext(context) {
			const displayEntity = String(context?.displayEntity || '');
			if (!this.config?.read_only || !this._hass || !displayEntity) {
				return displayEntity;
			}

			const statusEntity = this._resolveStatusEntity(displayEntity);
			const status = String(this._hass.states[statusEntity]?.state || '').toLowerCase();

			if (TIMER_REMAINING_RE.test(displayEntity)) {
				const durationEntity = displayEntity.replace(/^sensor\./, 'text.').replace(/_remaining(?:_friendly)?$/, '_duration');
				if (status === 'inactive' && this._hass.states[durationEntity]) {
					return durationEntity;
				}
			}

			if (ALARM_REMAINING_RE.test(displayEntity)) {
				const timeEntity = displayEntity.replace(/^sensor\./, 'text.').replace(/_remaining(?:_friendly)?$/, '_time');
				if (status !== 'snoozed' && this._hass.states[timeEntity]) {
					return timeEntity;
				}
			}

			return displayEntity;
		}

		_getMqttPrefix() {
			return String(this.config?.mqtt_prefix || '').trim() || 'snoozefest';
		}

		_deriveSelectedEntityKind(selector = String(this.config?.tap_sets_timer_id || '')) {
			if (selector.endsWith('_alarm_id')) return 'alarm';
			if (selector.endsWith('_timer_id')) return 'timer';
			return null;
		}

		_deriveSelectedEntityId(selector = String(this.config?.tap_sets_timer_id || '')) {
			if (!selector || !this._hass) return null;
			const rawId = String(this._hass.states[selector]?.state || '').trim();
			return rawId && rawId !== 'unknown' && rawId !== 'unavailable' ? rawId : null;
		}

		_deriveTimerId() {
			return this._resolveEntityContext().id;
		}

		_getDerivedSwitchEntity() {
			return this._resolveEntityContext().switchEntity;
		}

		_onCardPointerDown(ev) {
			if (!this.config.tap_sets_timer_id && !this.config.hold_dismisses) return;
			if (ev.target && ev.target.closest('input, button')) return;
			this._holdFired = false;
			this._holdTimer = setTimeout(() => {
				this._holdFired = true;
				this._doHold();
			}, 500);
		}

		_onCardPointerUp(ev) {
			if (!this.config.tap_sets_timer_id && !this.config.hold_dismisses) return;
			clearTimeout(this._holdTimer);
			this._holdTimer = null;
			if (this._holdFired) return;
			if (ev.target && ev.target.closest('input, button')) return;
			this._doTap();
		}

		_onCardPointerCancel() {
			clearTimeout(this._holdTimer);
			this._holdTimer = null;
		}

		_doTap() {
			if (!this._hass || !this.config.tap_sets_timer_id) return;
			const id = this._deriveTimerId();
			if (!id) return;
			this._hass.callService('input_text', 'set_value', {
				entity_id: this.config.tap_sets_timer_id,
				value: id,
			});
		}

		_doHold() {
			if (!this._hass || !this.config.hold_dismisses) return;
			const dismissButtonEntity = this._resolveEntityContext().dismissButtonEntity;
			if (!dismissButtonEntity) return;
			this._hass.callService('button', 'press', {
				entity_id: dismissButtonEntity,
			});
		}

		_doRemove() {
			if (!this._hass) return;
			const removeButtonEntity = this._resolveEntityContext().removeButtonEntity;
			if (!removeButtonEntity) return;
			this._hass.callService('button', 'press', {
				entity_id: removeButtonEntity,
			});
		}

		_secondaryHasClickAction() {
			return String(this.config?.secondary_click_action || 'none').toLowerCase() !== 'none';
		}

		_secondaryButtonHasClickAction() {
			return String(this.config?.secondary_button_click_action || 'none').toLowerCase() !== 'none';
		}

		_runSecondaryAction(action, service, explicitEntity, payloadObj) {
			if (!this._hass || !this.config || action === 'none') {
				return;
			}

			if (action === 'tap_select') {
				this._doTap();
				return;
			}
			if (action === 'dismiss') {
				this._doHold();
				return;
			}
			if (action === 'remove') {
				this._doRemove();
				return;
			}
			if (action === 'toggle_switch') {
				const entity = String(explicitEntity || this._getDerivedSwitchEntity() || '').trim();
				if (!entity) return;
				this._hass.callService('switch', 'toggle', { entity_id: entity });
				return;
			}
			if (action === 'service') {
				const svc = String(service || '').trim();
				if (!svc || !svc.includes('.')) return;
				const split = svc.split('.');
				const domain = split[0];
				const serviceName = split.slice(1).join('.');
				if (!domain || !serviceName) return;
				const payload = payloadObj && typeof payloadObj === 'object' ? { ...payloadObj } : {};
				const entity = String(explicitEntity || '').trim();
				if (entity) {
					payload.entity_id = entity;
				}
				this._hass.callService(domain, serviceName, payload);
			}
		}

		_onSecondaryClick(ev) {
			if (!this._hass || !this.config) return;
			if (this.config.secondary_click_stop_propagation !== false) {
				ev.preventDefault();
				ev.stopPropagation();
			}
			this._runSecondaryAction(
				String(this.config.secondary_click_action || 'none').toLowerCase(),
				this.config.secondary_click_service,
				this.config.secondary_click_entity,
				this.config.secondary_click_data,
			);
		}

		_onSecondaryButtonClick(ev) {
			if (!this._hass || !this.config) return;
			if (this.config.secondary_button_click_stop_propagation !== false) {
				ev.preventDefault();
				ev.stopPropagation();
			}
			this._runSecondaryAction(
				String(this.config.secondary_button_click_action || 'none').toLowerCase(),
				this.config.secondary_button_click_service,
				this.config.secondary_button_click_entity,
				this.config.secondary_button_click_data,
			);
		}

		_getCurrentStatus() {
			if (!this._hass || !this.config) return '';
			const statusEntity = this._getDerivedStatusEntity();
			return String(this._hass.states[statusEntity]?.state || '').toLowerCase();
		}

		_isStatusColorTargetEnabled(target) {
			const mode = String(this.config?.status_color_target || 'input').toLowerCase();
			return mode === 'both' || mode === target;
		}

		_getStatusColor(status) {
			if (!status) {
				return this.config.status_color_default ?? null;
			}
			const key = `status_color_${status}`;
			return this.config[key] ?? this.config.status_color_default ?? null;
		}

		_getStatusOpacity(status) {
			if (!status) {
				return this.config.status_opacity_default ?? null;
			}
			const key = `status_opacity_${status}`;
			return this.config[key] ?? this.config.status_opacity_default ?? null;
		}

		_getDerivedStatusEntity() {
			return this._resolveEntityContext().statusEntity;
		}

		_resolveStatusEntity(displayEntity) {
			if (this.config?.status_entity) return this.config.status_entity;
			if (!displayEntity) return null;
			if (TIMER_REMAINING_RE.test(displayEntity)) return displayEntity.replace(/_remaining(?:_friendly)?$/, '_status');
			if (ALARM_REMAINING_RE.test(displayEntity)) return displayEntity.replace(/_remaining(?:_friendly)?$/, '_status');
			if (TIMER_DURATION_RE.test(displayEntity)) return displayEntity.replace(/^(text|input_text)\./, 'sensor.').replace(/_duration$/, '_status');
			if (ALARM_TIME_RE.test(displayEntity)) return displayEntity.replace(/^(text|input_text)\./, 'sensor.').replace(/_time$/, '_status');
			return null;
		}

		_getResolvedInputBackground(status) {
			if (!this._hass || !this.config) {
				return this.config?.input_background ?? null;
			}
			if (this._isStatusColorTargetEnabled('input')) {
				const statusColor = this._getStatusColor(status);
				if (statusColor != null) return statusColor;
			}
			return this.config.input_background;
		}

		_getResolvedCardBackground(status) {
			if (!this._hass || !this.config) {
				return this.config?.card_background ?? null;
			}
			if (this._isStatusColorTargetEnabled('card')) {
				const statusColor = this._getStatusColor(status);
				if (statusColor != null) return statusColor;
			}
			return this.config.card_background;
		}

		_normalizeFlexPosition(value, axis) {
			const normalized = String(value || '').toLowerCase();
			if (normalized === 'left' || normalized === 'start' || normalized === 'flex-start') return 'flex-start';
			if (normalized === 'right' || normalized === 'end' || normalized === 'flex-end') return 'flex-end';
			if (normalized === 'top' && axis === 'vertical') return 'flex-start';
			if (normalized === 'bottom' && axis === 'vertical') return 'flex-end';
			if (normalized === 'middle') return 'center';
			if (normalized === 'stretch' && axis === 'vertical') return 'stretch';
			return 'center';
		}

		_getActiveSegments() {
			return this._getVisibleSegmentKeys().map((key) => {
				const definition = SEGMENT_DEFINITIONS[key];
				return {
					key,
					prop: definition.prop,
					max: definition.max,
					placeholder: this.config[definition.placeholderKey] || definition.fallbackPlaceholder,
					unit: this.config[definition.unitKey],
				};
			});
		}

		_getVisibleSegmentKeys() {
			const keys = [];
			if (this.config.show_days) keys.push('days');
			keys.push('hours', 'minutes');
			if (this.config.show_seconds) keys.push('seconds');
			return keys;
		}

		_getSegmentDefinition(segKey) {
			return SEGMENT_DEFINITIONS[segKey] || null;
		}

		_getSegmentText(segKey) {
			const definition = this._getSegmentDefinition(segKey);
			return definition ? String(this[definition.prop] || '') : '';
		}

		_setSegmentText(segKey, value) {
			const definition = this._getSegmentDefinition(segKey);
			if (!definition) return;
			this[definition.prop] = this._digitsOnly(value);
		}

		_getEntityIdForValueParsing() {
			return String(this.stateObj?.entity_id || this.config?.display_entity || '');
		}

		_getEntityIdForValueWriting() {
			return String(this.config?.entity || this.stateObj?.entity_id || '');
		}

		_isTimerValueEntity(entityId) {
			return TIMER_VALUE_ENTITY_RE.test(String(entityId || ''));
		}

		_parseRawStateParts(raw) {
			return String(raw || '').split(':').map((part) => this._digitsOnly(part));
		}

		_normalizeTimerParts(parts) {
			const normalized = [...(parts || [])].map((part) => this._digitsOnly(part));
			if (normalized.length > 4) {
				return normalized.slice(-4);
			}
			while (normalized.length < 4) {
				normalized.unshift('00');
			}
			return normalized;
		}

		_parseStateToVisibleSegments(raw, entityId = this._getEntityIdForValueParsing()) {
			const rawParts = this._parseRawStateParts(raw);
			const visibleKeys = this._getVisibleSegmentKeys();

			if (this._isTimerValueEntity(entityId)) {
				const timerParts = this._normalizeTimerParts(rawParts);
				const timerMap = {
					days: timerParts[0],
					hours: timerParts[1],
					minutes: timerParts[2],
					seconds: timerParts[3],
				};
				return visibleKeys.map((key) => timerMap[key] || '');
			}

			return visibleKeys.map((key, index) => {
				void key;
				return rawParts[index] || '';
			});
		}

		_serializeVisibleSegmentsToValue(entityId = this._getEntityIdForValueWriting()) {
			const visibleKeys = this._getVisibleSegmentKeys();
			const visibleValues = Object.fromEntries(
				visibleKeys.map((key) => [key, String(parseInt(this._getSegmentText(key) || '0', 10) || 0).padStart(2, '0')]),
			);

			if (this._isTimerValueEntity(entityId)) {
				return [
					visibleValues.days || '00',
					visibleValues.hours || '00',
					visibleValues.minutes || '00',
					visibleValues.seconds || '00',
				].join(':');
			}

			return visibleKeys.map((key) => visibleValues[key] || '00').join(':');
		}

		_getSuffixStyle() {
			return [
				this.config.suffix_font_size != null ? `font-size: ${this.config.suffix_font_size}` : '',
				this.config.suffix_color != null ? `color: ${this.config.suffix_color}` : '',
				this.config.suffix_padding != null ? `padding: ${this.config.suffix_padding}` : '',
				this.config.suffix_opacity != null ? `opacity: ${this.config.suffix_opacity}` : '',
			].filter(Boolean).join('; ');
		}

		_getSecondaryPosition() {
			const anchor = this._getSecondaryAnchor();
			const raw = String(this.config?.secondary_position || (anchor === 'card' ? 'center' : 'below')).toLowerCase();
			return this._normalizeOverlayPosition(raw, anchor, anchor === 'card' ? 'center' : 'below');
		}

		_getSecondaryAnchor() {
			return String(this.config?.secondary_anchor || 'content').toLowerCase() === 'card' ? 'card' : 'content';
		}

		_getSecondaryButtonAnchor() {
			const raw = this.config?.secondary_button_anchor;
			if (raw == null || raw === '') return this._getSecondaryAnchor();
			return String(raw).toLowerCase() === 'card' ? 'card' : 'content';
		}

		_getSecondaryButtonPosition() {
			const anchor = this._getSecondaryButtonAnchor();
			const fallback = anchor === 'card' ? 'center' : 'right';
			const raw = String(this.config?.secondary_button_position || fallback).toLowerCase();
			return this._normalizeOverlayPosition(raw, anchor, fallback);
		}

		_normalizeOverlayPosition(position, anchor, fallback) {
			if (anchor === 'card') {
				return CARD_ANCHOR_POSITIONS.has(position) ? position : fallback;
			}
			return CONTENT_ANCHOR_POSITIONS.has(position) ? position : fallback;
		}

		_getContentFlowPosition(position) {
			const pos = String(position || '').toLowerCase();
			if (pos === 'left' || pos === 'centerleft') return 'left';
			if (pos === 'right' || pos === 'centerright') return 'right';
			if (pos === 'above' || pos === 'top' || pos === 'topleft' || pos === 'topcenter' || pos === 'topright') return 'above';
			if (pos === 'below' || pos === 'bottom' || pos === 'bottomleft' || pos === 'bottomcenter' || pos === 'bottomright') return 'below';
			return 'below';
		}

		_getSecondaryButtonAlign(position) {
			const align = this.config?.secondary_button_align != null ? String(this.config.secondary_button_align).toLowerCase() : '';
			if (align === 'left' || align === 'center' || align === 'right') return align;
			if (position === 'right' || position === 'topright' || position === 'bottomright' || position === 'centerright') return 'right';
			if (position === 'left' || position === 'topleft' || position === 'bottomleft' || position === 'centerleft') return 'left';
			return 'center';
		}

		_getSecondaryAlign() {
			const align = this.config?.secondary_align != null ? String(this.config.secondary_align).toLowerCase() : '';
			if (align === 'left' || align === 'center' || align === 'right') return align;
			const position = this._getSecondaryPosition();
			if (position === 'right' || position === 'topright' || position === 'bottomright' || position === 'centerright') return 'right';
			if (position === 'left' || position === 'topleft' || position === 'bottomleft' || position === 'centerleft') return 'left';
			return 'center';
		}

		_getBinaryState(entityId) {
			const raw = this._getSecondaryEntityState(entityId).toLowerCase();
			if (!raw) return null;
			if (raw === 'on' || raw === 'true' || raw === 'active' || raw === 'paused' || raw === 'ringing' || raw === 'snoozed') return 'on';
			if (raw === 'off' || raw === 'false' || raw === 'inactive') return 'off';
			return null;
		}

		_getOverlayStateEntity(type) {
			const isButton = type === 'button';
			const explicit = isButton
				? this.config.secondary_button_icon_state_entity
				: this.config.secondary_icon_state_entity;
			if (explicit) return explicit;

			const context = this._resolveEntityContext();
			if (context.switchEntity && this._hass?.states?.[context.switchEntity]) {
				return context.switchEntity;
			}
			if (context.statusEntity && this._hass?.states?.[context.statusEntity]) {
				return context.statusEntity;
			}
			return context.switchEntity || context.statusEntity || null;
		}

		_getResolvedStateIcon(defaultIcon, stateEntity, iconOn, iconOff) {
			const fallback = String(defaultIcon || '').trim();
			const state = this._getBinaryState(stateEntity);
			if (state === 'on') return String(iconOn || fallback).trim();
			if (state === 'off') return String(iconOff || fallback).trim();
			return fallback;
		}

		_getLargestCssSize(values) {
			const parsed = (values || [])
				.map((v) => String(v || '').trim())
				.filter(Boolean)
				.map((raw) => {
					const m = raw.match(/^(-?\d*\.?\d+)([a-z%]+)$/i);
					if (!m) return null;
					return { raw, num: parseFloat(m[1]), unit: String(m[2] || '').toLowerCase() };
				})
				.filter(Boolean);
			if (!parsed.length) return null;
			const unit = parsed[0].unit;
			if (!parsed.every((p) => p.unit === unit && Number.isFinite(p.num))) return null;
			let max = parsed[0].num;
			for (const p of parsed) {
				if (p.num > max) max = p.num;
			}
			return `${max}${unit}`;
		}

		_getSecondaryCardPositionStyle(position) {
			switch (position) {
				case 'top':
				case 'topcenter':
					return 'top: 0; left: 50%; transform: translateX(-50%)';
				case 'bottom':
				case 'bottomcenter':
					return 'bottom: 0; left: 50%; transform: translateX(-50%)';
				case 'left':
				case 'centerleft':
					return 'left: 0; top: 50%; transform: translateY(-50%)';
				case 'right':
				case 'centerright':
					return 'right: 0; top: 50%; transform: translateY(-50%)';
				case 'topleft':
					return 'top: 0; left: 0';
				case 'topright':
					return 'top: 0; right: 0';
				case 'bottomleft':
					return 'bottom: 0; left: 0';
				case 'bottomright':
					return 'bottom: 0; right: 0';
				case 'center':
				default:
					return 'left: 50%; top: 50%; transform: translate(-50%, -50%)';
			}
		}

		_getSecondaryEntityState(entityId) {
			if (!entityId || !this._hass) return '';
			const raw = String(this._hass.states[entityId]?.state || '').trim();
			if (!raw || raw === 'unknown' || raw === 'unavailable' || raw === 'None') return '';
			return raw;
		}

		_titleCaseWords(value) {
			return String(value || '')
				.split(/\s+/)
				.filter(Boolean)
				.map((w) => w.charAt(0).toUpperCase() + w.slice(1))
				.join(' ');
		}

		_getSecondaryText(currentStatus) {
			const mode = String(this.config?.secondary_mode || 'none').toLowerCase();
			if (mode === 'none') return '';
			if (mode === 'label') return String(this.config?.secondary_text || '');
			if (mode === 'status') return currentStatus ? this._titleCaseWords(currentStatus) : '';
			if (mode === 'entity') return this._getSecondaryEntityState(this.config?.secondary_entity);

			const { base, kind } = this._resolveEntityContext();
			if (!base) return '';

			if (mode === 'weekday_smart' || mode === 'smart_weekday') {
				if (kind !== 'alarm') {
					return this._getSecondaryEntityState(this._resolveEntityContext().nextDayEntity);
				}
				const selected = [];
				for (let wd = 0; wd < this._resolveEntityContext().weekdaySwitchEntities.length; wd += 1) {
					const state = this._getSecondaryEntityState(this._resolveEntityContext().weekdaySwitchEntities[wd]).toLowerCase();
					if (state === 'on' || state === 'true') {
						selected.push(wd);
					}
				}
				if (selected.length === 0 || selected.length === 7) {
					return this._getSecondaryEntityState(this._resolveEntityContext().nextDayEntity);
				}
				return selected.map((wd) => DAY_LABELS[wd] || '').filter(Boolean).join(' ');
			}

			if (mode === 'remaining') {
				const context = this._resolveEntityContext();
				return this._getSecondaryEntityState(context.friendlyRemainingEntity) || this._getSecondaryEntityState(context.remainingEntity);
			}
			if (mode === 'weekday') {
				return this._getSecondaryEntityState(this._resolveEntityContext().nextDayEntity);
			}
			return '';
		}

		_buildCardStyle(currentStatus) {
			const resolvedInputBackground = this._getResolvedInputBackground(currentStatus);
			const resolvedCardBackground = this._getResolvedCardBackground(currentStatus);
			return [
				resolvedCardBackground != null ? `--ha-card-background: ${resolvedCardBackground}` : '',
				this.config.card_border === false ? '--ha-card-border-width: 0; --ha-card-box-shadow: none' : '',
				this.config.color != null ? `color: ${this.config.color}` : '',
				this.config.font_size != null ? `font-size: ${this.config.font_size}em` : '',
				this.config.content_justify != null ? `--stpc-justify-content: ${this.config.content_justify}` : '',
				this.config.content_align != null ? `--stpc-align-items: ${this.config.content_align}` : '',
				this.config.padding != null ? `padding: ${this.config.padding}` : '',
				this.config.padding_top_bottom != null ? `padding-top: ${this.config.padding_top_bottom}; padding-bottom: ${this.config.padding_top_bottom}` : '',
				this.config.padding_left_right != null ? `padding-left: ${this.config.padding_left_right}; padding-right: ${this.config.padding_left_right}` : '',
				this.config.padding_top != null ? `padding-top: ${this.config.padding_top}` : '',
				this.config.padding_bottom != null ? `padding-bottom: ${this.config.padding_bottom}` : '',
				this.config.padding_left != null ? `padding-left: ${this.config.padding_left}` : '',
				this.config.padding_right != null ? `padding-right: ${this.config.padding_right}` : '',
				this.config.input_width != null ? `--stpc-input-width: ${this.config.input_width}` : '',
				this.config.content_offset_x != null ? `--stpc-main-offset-x: ${this.config.content_offset_x}` : '',
				this.config.content_offset_y != null ? `--stpc-main-offset-y: ${this.config.content_offset_y}` : '',
				this.config.stepper_size != null ? `--stpc-stepper-size: ${this.config.stepper_size}` : '',
				this.config.stepper_hit_height != null ? `--stpc-stepper-hit-height: ${this.config.stepper_hit_height}` : '',
				this.config.stepper_color != null ? `--stpc-stepper-color: ${this.config.stepper_color}` : '',
				this.config.stepper_opacity != null ? `--stpc-stepper-opacity: ${this.config.stepper_opacity}` : '',
				this.config.stepper_active_opacity != null ? `--stpc-stepper-active-opacity: ${this.config.stepper_active_opacity}` : '',
				this.config.stepper_input_pad_y != null ? `--stpc-stepper-input-pad-y: ${this.config.stepper_input_pad_y}` : '',
				this.config.stepper_offset != null ? `--stpc-stepper-offset: ${this.config.stepper_offset}` : '',
				this.config.stepper_stroke != null ? `--stpc-stepper-stroke: ${this.config.stepper_stroke}` : '',
				resolvedInputBackground != null ? `--stpc-input-background: ${resolvedInputBackground}` : '',
				this.config.input_padding != null ? `--stpc-input-padding: ${this.config.input_padding}` : '',
				this.config.input_border_radius != null ? `--stpc-input-border-radius: ${this.config.input_border_radius}` : '',
			].filter(Boolean).join('; ');
		}

		_getOverlayBaseDescriptor(type) {
			const isButton = type === 'button';
			const enabled = isButton ? this.config.secondary_button === true : true;
			const anchor = isButton ? this._getSecondaryButtonAnchor() : this._getSecondaryAnchor();
			const position = isButton ? this._getSecondaryButtonPosition() : this._getSecondaryPosition();
			const flowPosition = this._getContentFlowPosition(position);
			const align = isButton ? this._getSecondaryButtonAlign(position) : this._getSecondaryAlign();
			const clickable = isButton ? this._secondaryButtonHasClickAction() : this._secondaryHasClickAction();
			return {
				type,
				enabled,
				anchor,
				position,
				flowPosition,
				align,
				clickable,
			};
		}

		_getOverlayStatefulIcon(type, fallbackIcon) {
			const isButton = type === 'button';
			const stateEntity = this._getOverlayStateEntity(type);
			const state = this._getBinaryState(stateEntity);
			const color = isButton
				? (state === 'on' ? this.config.secondary_button_icon_on_color : (state === 'off' ? this.config.secondary_button_icon_off_color : null))
				: (state === 'on' ? this.config.secondary_icon_on_color : (state === 'off' ? this.config.secondary_icon_off_color : null));
			const opacity = isButton
				? (state === 'on' ? this.config.secondary_button_icon_on_opacity : (state === 'off' ? this.config.secondary_button_icon_off_opacity : null))
				: (state === 'on' ? this.config.secondary_icon_on_opacity : (state === 'off' ? this.config.secondary_icon_off_opacity : null));
			const icon = isButton
				? this._getResolvedStateIcon(
					this.config.secondary_button_icon || fallbackIcon,
					stateEntity,
					this.config.secondary_button_icon_on,
					this.config.secondary_button_icon_off,
				)
				: this._getResolvedStateIcon(
					this.config.secondary_icon || fallbackIcon,
					stateEntity,
					this.config.secondary_icon_on,
					this.config.secondary_icon_off,
				);
			return {
				stateEntity,
				state,
				color,
				opacity,
				icon: icon || fallbackIcon,
			};
		}

		_buildOverlayStyle(descriptor, options = {}) {
			const {
				fontSize,
				baseColor,
				stateColor,
				opacity,
				stateOpacity,
				fontWeight,
				padding,
				offsetX,
				offsetY,
				zIndex,
				pointerEvents,
				background,
				borderRadius,
				iconSizeVar,
				iconSize,
				fixedSize,
			} = options;

			return [
				fontSize != null ? `font-size: ${fontSize}` : '',
				baseColor != null ? `color: ${baseColor}` : '',
				stateColor != null ? `color: ${stateColor}` : '',
				opacity != null ? `opacity: ${opacity}` : '',
				stateOpacity != null ? `opacity: ${stateOpacity}` : '',
				fontWeight != null ? `font-weight: ${fontWeight}` : '',
				padding != null ? `padding: ${padding}` : '',
				offsetX != null ? `margin-left: ${offsetX}` : '',
				offsetY != null ? `margin-top: ${offsetY}` : '',
				zIndex != null ? `z-index: ${zIndex}` : '',
				descriptor.clickable ? 'pointer-events: auto' : (pointerEvents != null ? `pointer-events: ${pointerEvents}` : ''),
				`text-align: ${descriptor.align}`,
				iconSizeVar && iconSize != null ? `${iconSizeVar}: ${iconSize}` : '',
				background != null ? `background: ${background}` : '',
				borderRadius != null ? `border-radius: ${borderRadius}` : '',
				fixedSize != null ? `width: ${fixedSize}` : '',
				fixedSize != null ? `height: ${fixedSize}` : '',
				fixedSize != null ? `min-width: ${fixedSize}` : '',
				fixedSize != null ? `min-height: ${fixedSize}` : '',
				fixedSize != null ? 'display: inline-flex' : '',
				fixedSize != null ? 'align-items: center' : '',
				fixedSize != null ? 'justify-content: center' : '',
				descriptor.anchor === 'content' && descriptor.flowPosition === 'right' ? 'margin-left: auto' : '',
				descriptor.anchor === 'content' && descriptor.flowPosition === 'left' ? 'margin-right: auto' : '',
				descriptor.anchor === 'card' ? this._getSecondaryCardPositionStyle(descriptor.position) : '',
			].filter(Boolean).join('; ');
		}

		_buildSecondaryTextDescriptor(currentStatus) {
			const descriptor = this._getOverlayBaseDescriptor('secondary');
			const variant = String(this.config.secondary_variant || 'text').toLowerCase() === 'icon' ? 'icon' : 'text';
			const text = this._getSecondaryText(currentStatus);
			const iconState = this._getOverlayStatefulIcon('secondary', 'mdi:information-outline');
			const style = this._buildOverlayStyle(descriptor, {
				fontSize: this.config.secondary_font_size,
				baseColor: this.config.secondary_color,
				stateColor: variant === 'icon' ? iconState.color : null,
				opacity: this.config.secondary_opacity,
				stateOpacity: variant === 'icon' ? iconState.opacity : null,
				fontWeight: this.config.secondary_font_weight,
				padding: this.config.secondary_padding,
				offsetX: this.config.secondary_offset_x,
				offsetY: this.config.secondary_offset_y,
				zIndex: this.config.secondary_z_index,
				pointerEvents: this.config.secondary_pointer_events,
				background: variant === 'icon' ? this.config.secondary_icon_background : null,
				borderRadius: variant === 'icon' ? this.config.secondary_icon_border_radius : null,
				iconSizeVar: variant === 'icon' ? '--stpc-secondary-icon-size' : null,
				iconSize: variant === 'icon' ? this.config.secondary_icon_size : null,
			});
			return {
				...descriptor,
				variant,
				text,
				icon: iconState.icon,
				label: this.config.secondary_aria_label || text || 'Secondary action',
				style,
				shouldRender: variant === 'icon' ? Boolean(iconState.icon) : Boolean(text),
			};
		}

		_buildSecondaryButtonDescriptor() {
			const descriptor = this._getOverlayBaseDescriptor('button');
			const iconState = this._getOverlayStatefulIcon('button', 'mdi:dots-horizontal');
			const fixedSize = this._getLargestCssSize([this.config.secondary_button_icon_size]);
			const style = this._buildOverlayStyle(descriptor, {
				baseColor: this.config.secondary_color,
				stateColor: iconState.color,
				stateOpacity: iconState.opacity,
				padding: this.config.secondary_button_icon_padding,
				offsetX: this.config.secondary_button_offset_x,
				offsetY: this.config.secondary_button_offset_y,
				zIndex: this.config.secondary_button_z_index,
				pointerEvents: this.config.secondary_button_pointer_events,
				background: this.config.secondary_button_icon_background,
				borderRadius: this.config.secondary_button_icon_border_radius,
				iconSizeVar: '--stpc-secondary-btn-icon-size',
				iconSize: this.config.secondary_button_icon_size,
				fixedSize,
			});
			return {
				...descriptor,
				variant: 'icon',
				text: '',
				icon: iconState.icon,
				label: this.config.secondary_button_aria_label || 'Secondary button action',
				style,
				shouldRender: descriptor.enabled && Boolean(iconState.icon),
			};
		}

		_buildOverlayDescriptor(type, currentStatus) {
			return type === 'button'
				? this._buildSecondaryButtonDescriptor()
				: this._buildSecondaryTextDescriptor(currentStatus);
		}

		_renderOverlay(descriptor) {
			if (!descriptor.shouldRender) return '';
			const content = descriptor.variant === 'icon'
				? html`<ha-icon icon="${descriptor.icon}"></ha-icon>`
				: descriptor.text;
			const title = descriptor.text || descriptor.label;

			if (descriptor.clickable) {
				const handler = descriptor.type === 'button' ? this._onSecondaryButtonClick : this._onSecondaryClick;
				return html`<button type="button" class="secondary secondary-btn ${descriptor.variant} anchor-${descriptor.anchor}" style="${descriptor.style}" title="${title}" aria-label="${descriptor.label}" @click="${handler}">${content}</button>`;
			}

			return html`<div class="secondary ${descriptor.variant} anchor-${descriptor.anchor}" style="${descriptor.style}" title="${title}">${content}</div>`;
		}

		_renderMissingEntityCard() {
			return html`
				<ha-card .hass="${this._hass}" .config="${this.config}">
					<div class="wrapper">
						<span class="missing-entity">Missing entity: ${this.config?.display_entity || this.config?.entity || ''}</span>
					</div>
				</ha-card>
			`;
		}

		_renderMainMarkup(interactive) {
			return html`
				<div class="wrapper">
					${this._getActiveSegments().map((seg, i) => html`
						${this.config.separator_mode === 'colon' && i > 0 ? html`<span class="separator" style="${this._getSuffixStyle()}">${this.config.separator}</span>` : ''}
						<div class="segment">
							<div class="${this.config.show_steppers ? 'input-wrap with-steppers' : 'input-wrap'}">
								<input
									class="input"
									inputmode="numeric"
									maxlength="2"
									?readonly="${this.config.read_only}"
									placeholder="${seg.placeholder}"
									.value="${this[seg.prop]}"
									@input="${(ev) => this._onInput(seg.key, ev)}"
									@focus="${this._onInputFocus}"
									@click="${this._onInputFocus}"
									@blur="${this._onCommit}"
									@keydown="${this._onKeydown}"
								/>
							</div>
							${this.config.show_steppers && interactive ? html`
								<button type="button" class="stepper-btn up" @pointerdown="${this._onStepperPointerDown}" @click="${() => this._stepSegment(seg.key, 1)}" aria-label="Increase ${seg.key}">
									<span class="stepper-glyph"></span>
								</button>
								<button type="button" class="stepper-btn down" @pointerdown="${this._onStepperPointerDown}" @click="${() => this._stepSegment(seg.key, -1)}" aria-label="Decrease ${seg.key}">
									<span class="stepper-glyph"></span>
								</button>
							` : ''}
						</div>
						${this.config.separator_mode === 'units' ? html`<span class="separator" style="${this._getSuffixStyle()}">${seg.unit}</span>` : ''}
					`)}
				</div>
			`;
		}

		_getContentFlowPositionForDescriptors(secondary, secondaryButton) {
			if (secondary.anchor === 'content' && secondary.shouldRender) {
				return secondary.flowPosition;
			}
			if (secondaryButton.anchor === 'content' && secondaryButton.shouldRender) {
				return secondaryButton.flowPosition;
			}
			return 'below';
		}

		_buildContentStyle(secondary, contentFlowPosition) {
			return [
				this.config.secondary_gap != null ? `--stpc-secondary-gap: ${this.config.secondary_gap}` : '',
				secondary.anchor === 'content' && (contentFlowPosition === 'below' || contentFlowPosition === 'above') && secondary.align === 'left' ? 'align-items: flex-start' : '',
				secondary.anchor === 'content' && (contentFlowPosition === 'below' || contentFlowPosition === 'above') && secondary.align === 'center' ? 'align-items: center' : '',
				secondary.anchor === 'content' && (contentFlowPosition === 'below' || contentFlowPosition === 'above') && secondary.align === 'right' ? 'align-items: flex-end' : '',
			].filter(Boolean).join('; ');
		}

		_renderCardContent(mainMarkup, secondary, secondaryButton, currentStatus) {
			const secondaryMarkup = this._renderOverlay(secondary);
			const secondaryButtonMarkup = this._renderOverlay(secondaryButton);
			const contentFlowPosition = this._getContentFlowPositionForDescriptors(secondary, secondaryButton);
			const contentStyle = this._buildContentStyle(secondary, contentFlowPosition);
			const mainStyle = this._getStatusOpacity(currentStatus) != null ? `opacity: ${this._getStatusOpacity(currentStatus)}` : '';

			return html`
				<div class="content anchor-${secondary.anchor} pos-${contentFlowPosition}" style="${contentStyle}">
					${secondary.anchor === 'content' && secondary.shouldRender && (secondary.flowPosition === 'above' || secondary.flowPosition === 'left') ? secondaryMarkup : ''}
					${secondaryButton.anchor === 'content' && secondaryButton.shouldRender && (secondaryButton.flowPosition === 'above' || secondaryButton.flowPosition === 'left') ? secondaryButtonMarkup : ''}
					<div class="main" style="${mainStyle}">${mainMarkup}</div>
					${secondary.anchor === 'content' && secondary.shouldRender && (secondary.flowPosition === 'below' || secondary.flowPosition === 'right') ? secondaryMarkup : ''}
					${secondaryButton.anchor === 'content' && secondaryButton.shouldRender && (secondaryButton.flowPosition === 'below' || secondaryButton.flowPosition === 'right') ? secondaryButtonMarkup : ''}
					${secondary.anchor === 'card' && secondary.shouldRender ? secondaryMarkup : ''}
					${secondaryButton.anchor === 'card' && secondaryButton.shouldRender ? secondaryButtonMarkup : ''}
				</div>
			`;
		}

		render() {
			if (!this.stateObj) {
				return this._renderMissingEntityCard();
			}

			const interactive = !this.config.read_only;
			const currentStatus = this._getCurrentStatus();
			const cardStyle = this._buildCardStyle(currentStatus);
			const secondary = this._buildOverlayDescriptor('secondary', currentStatus);
			const secondaryButton = this._buildOverlayDescriptor('button', currentStatus);
			const mainMarkup = this._renderMainMarkup(interactive);

			return html`
				<ha-card
					.hass="${this._hass}"
					.config="${this.config}"
					style="${cardStyle}${this.config.tap_sets_timer_id || this.config.hold_dismisses ? '; cursor: pointer' : ''}"
					@pointerdown="${this._onCardPointerDown}"
					@pointerup="${this._onCardPointerUp}"
					@pointercancel="${this._onCardPointerCancel}"
				>
					${this.config.title ? html`<div class="card-header">${this.config.title}</div>` : ''}
					${this._renderCardContent(mainMarkup, secondary, secondaryButton, currentStatus)}
				</ha-card>
			`;
		}

		_onStepperPointerDown(ev) {
			if (this.config.read_only) return;
			ev.preventDefault();
		}

		_stepSegment(segKey, delta) {
			if (this.config.read_only) return;
			const seg = this._getActiveSegments().find((item) => item.key === segKey);
			if (!seg) return;
			const current = parseInt(this._getSegmentText(segKey) || '0', 10);
			const currentNum = Number.isNaN(current) ? 0 : current;
			let next = currentNum + delta;
			if (this.config.stepper_wrap) {
				const span = seg.max + 1;
				next = ((next % span) + span) % span;
			} else {
				next = Math.max(0, Math.min(seg.max, next));
			}
			this._setSegmentText(segKey, String(next).padStart(2, '0'));
			if (this.config.autosave) this._save();
		}

		_onInput(segKey, ev) {
			if (this.config.read_only) return;
			const val = this._digitsOnly(ev.target.value);
			ev.target.value = val;
			this._setSegmentText(segKey, val);
			const segs = this._getActiveSegments();
			if (this.config.autosave && segs.every((s) => this._getSegmentText(s.key).length === 2)) {
				this._save();
			}
		}

		_onInputFocus(ev) {
			if (this.config.read_only) return;
			const input = ev.target;
			if (!(input instanceof HTMLInputElement)) return;
			requestAnimationFrame(() => {
				if (this.shadowRoot?.activeElement !== input) return;
				input.select();
			});
		}

		_onKeydown(ev) {
			if (this.config.read_only || ev.key !== 'Enter') return;
			ev.preventDefault();
			this._save();
			ev.target.blur();
		}

		_onCommit() {
			if (this.config.read_only) return;
			if (this.config.autosave) this._save();
		}

		_syncFromState() {
			if (this.shadowRoot && this.shadowRoot.activeElement) {
				return;
			}
			const raw = String(this.stateObj?.state || '');
			const now = Date.now();
			if (this._pendingValue) {
				if (raw === this._pendingValue) {
					this._clearPendingWrite();
				} else {
					const isKnownStale = this._pendingPrevValue != null && raw === this._pendingPrevValue;
					const staleHoldUntil = this._pendingSince + (Number.isFinite(this.config.pending_stale_ms) ? this.config.pending_stale_ms : 3000);
					if (now < this._pendingUntil || (isKnownStale && now < staleHoldUntil)) {
						return;
					}
					this._clearPendingWrite();
				}
			}
			const parts = this._parseStateToVisibleSegments(raw);
			this._getActiveSegments().forEach((seg, i) => {
				this._setSegmentText(seg.key, parts[i] || '');
			});
		}

		_clearPendingWrite() {
			this._pendingValue = null;
			this._pendingPrevValue = null;
			this._pendingSince = 0;
			this._pendingUntil = 0;
		}

		_digitsOnly(val) {
			return String(val || '').replace(/\D/g, '').slice(0, 2);
		}

		_save() {
			if (this.config.read_only || !this._hass || !this.stateObj || !this.config.entity) return;
			const segs = this._getActiveSegments();
			if (segs.every((s) => this._getSegmentText(s.key).length === 0)) return;
			const nums = segs.map((s) => parseInt(this._getSegmentText(s.key) || '0', 10));
			if (nums.some((n) => Number.isNaN(n))) return;
			if (segs.some((s, i) => nums[i] < 0 || nums[i] > s.max)) return;
			const value = this._serializeVisibleSegmentsToValue();
			const now = Date.now();
			this._pendingPrevValue = String(this.stateObj?.state || '');
			this._pendingValue = value;
			this._pendingSince = now;
			this._pendingUntil = now + (Number.isFinite(this.config.pending_write_ms) ? this.config.pending_write_ms : 700);
			const domain = this.config.entity.split('.')[0];
			this._hass.callService(domain, 'set_value', {
				entity_id: this.config.entity,
				value,
			});
		}

		getCardSize() {
			return 1;
		}
	}

	if (!customElements.get('snoozefest-entity-card')) {
		customElements.define('snoozefest-entity-card', SnoozefestEntityCard);
		console.info(
			`%c  snoozefest-entity-card \n%c  version: ${version}    `,
			'color: orange; font-weight: bold; background: black',
			'color: white; font-weight: bold; background: dimgray',
		);
	}
})(window.LitElement || Object.getPrototypeOf(customElements.get('hui-masonry-view') || customElements.get('hui-view')));