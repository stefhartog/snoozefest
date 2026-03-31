((LitElement) => {
	const html = LitElement.prototype.html;
	const css = LitElement.prototype.css;
const version = '0.3.8-custom';

	class SnoozefestTimePickerCard extends LitElement {
		constructor() {
			super();
			this._onKeydown = this._onKeydown.bind(this);
			this._onCommit = this._onCommit.bind(this);
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

			const readOnly = config.read_only === true;
			this.config = {
				entity: writeEntity,
				display_entity: displayEntity,
				status_entity: config.status_entity != null ? String(config.status_entity) : null,
				status_color_target: config.status_color_target != null ? String(config.status_color_target).toLowerCase() : 'input',
				tap_sets_timer_id: config.tap_sets_timer_id != null ? String(config.tap_sets_timer_id) : null,
				hold_dismisses: config.hold_dismisses === true,
				read_only: readOnly,
				title: config.title,
				autosave: readOnly ? false : (config.autosave !== false),
				content_justify: this._normalizeFlexPosition(config.content_justify || config.justify || 'left', 'horizontal'),
				content_align: this._normalizeFlexPosition(config.content_align || config.align || 'center', 'vertical'),
				show_days: config.show_days === true,
				show_seconds: config.show_seconds === true,
				days_placeholder: config.days_placeholder || 'DD',
				hour_placeholder: config.hour_placeholder || 'HH',
				minute_placeholder: config.minute_placeholder || 'MM',
				second_placeholder: config.second_placeholder || 'SS',
				separator_mode: config.separator_mode === 'units' ? 'units' : 'colon',
				separator: config.separator || ':',
				unit_suffix_days: config.unit_suffix_days || 'd',
				unit_suffix_hours: config.unit_suffix_hours || 'h',
				unit_suffix_minutes: config.unit_suffix_minutes || 'm',
				unit_suffix_seconds: config.unit_suffix_seconds || 's',
				suffix_font_size: config.suffix_font_size != null ? String(config.suffix_font_size) : null,
				suffix_color: config.suffix_color != null ? String(config.suffix_color) : null,
				suffix_padding: config.suffix_padding != null ? String(config.suffix_padding) : null,
				suffix_opacity: config.suffix_opacity != null ? String(config.suffix_opacity) : null,
				show_steppers: config.show_steppers === true,
				stepper_wrap: config.stepper_wrap !== false,
				stepper_size: config.stepper_size != null ? String(config.stepper_size) : null,
				stepper_hit_height: config.stepper_hit_height != null ? String(config.stepper_hit_height) : null,
				stepper_color: config.stepper_color != null ? String(config.stepper_color) : null,
				stepper_opacity: config.stepper_opacity != null ? String(config.stepper_opacity) : null,
				stepper_active_opacity: config.stepper_active_opacity != null ? String(config.stepper_active_opacity) : null,
				stepper_input_pad_y: config.stepper_input_pad_y != null ? String(config.stepper_input_pad_y) : null,
				stepper_offset: config.stepper_offset != null ? String(config.stepper_offset) : null,
				stepper_stroke: config.stepper_stroke != null ? String(config.stepper_stroke) : null,
				pending_write_ms: config.pending_write_ms != null ? parseInt(config.pending_write_ms, 10) : 700,
				pending_stale_ms: config.pending_stale_ms != null ? parseInt(config.pending_stale_ms, 10) : 3000,
				input_background: config.input_background != null ? String(config.input_background) : null,
				status_color_default: config.status_color_default != null ? String(config.status_color_default) : null,
				status_color_inactive: config.status_color_inactive != null ? String(config.status_color_inactive) : null,
				status_color_active: config.status_color_active != null ? String(config.status_color_active) : null,
				status_color_paused: config.status_color_paused != null ? String(config.status_color_paused) : null,
				status_color_ringing: config.status_color_ringing != null ? String(config.status_color_ringing) : null,
				input_padding: config.input_padding != null ? String(config.input_padding) : null,
				input_border_radius: config.input_border_radius != null ? String(config.input_border_radius) : null,
				card_border: config.card_border !== undefined ? config.card_border : null,
				card_background: config.card_background != null ? String(config.card_background) : null,
				color: config.color != null ? String(config.color) : null,
				font_size: config.font_size != null ? parseFloat(config.font_size) : null,
				padding: config.padding != null ? String(config.padding) : null,
				padding_left_right: config.padding_left_right != null ? String(config.padding_left_right) : null,
				padding_top_bottom: config.padding_top_bottom != null ? String(config.padding_top_bottom) : null,
				input_width: config.input_width != null ? String(config.input_width) : null,
			};
			this.daysText = '';
			this.hourText = '';
			this.minuteText = '';
			this.secondText = '';
		}

		set hass(hass) {
			this._hass = hass;
			if (!hass || !this.config) {
				return;
			}
			let resolvedDisplayEntity = this.config.display_entity;
			if (this.config.read_only && /^sensor\..+_timer_\d+_remaining$/.test(resolvedDisplayEntity || '')) {
				const statusEntity = resolvedDisplayEntity.replace(/_remaining$/, '_status');
				const durationEntity = resolvedDisplayEntity.replace(/^sensor\./, 'text.').replace(/_remaining$/, '_duration');
				const status = String(hass.states[statusEntity]?.state || '').toLowerCase();
				if (status === 'inactive' && hass.states[durationEntity]) {
					resolvedDisplayEntity = durationEntity;
				}
			}
			this.stateObj = hass.states[resolvedDisplayEntity] || null;
			if (!this.stateObj) {
				return;
			}
			this._syncFromState();
		}

		_deriveTimerBase() {
			const d = String(this.config?.display_entity || '');
			const m = d.match(/^sensor\.(.+_timer_\d+)_remaining(?:_friendly)?$/) ||
			          d.match(/^(?:text|input_text)\.(.+_timer_\d+)_duration$/);
			return m ? m[1] : null;
		}

		_deriveTimerId() {
			const base = this._deriveTimerBase();
			if (!base) return null;
			const m = base.match(/_timer_(\d+)$/);
			return m ? m[1] : null;
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
			const base = this._deriveTimerBase();
			if (!base) return;
			this._hass.callService('button', 'press', {
				entity_id: 'button.' + base + '_dismiss',
			});
		}

		_getCurrentStatus() {
			if (!this._hass || !this.config) {
				return '';
			}
			const statusEntity = this._getDerivedStatusEntity();
			return String(this._hass.states[statusEntity]?.state || '').toLowerCase();
		}

		_isStatusColorTargetEnabled(target) {
			const mode = String(this.config?.status_color_target || 'input').toLowerCase();
			if (mode === 'both') {
				return true;
			}
			return mode === target;
		}

		_getStatusColor(status) {
			if (!status) {
				return this.config.status_color_default ?? null;
			}
			const key = `status_color_${status}`;
			return this.config[key] ?? this.config.status_color_default ?? null;
		}

		_getDerivedStatusEntity() {
			if (!this.config) {
				return null;
			}
			if (this.config.status_entity) {
				return this.config.status_entity;
			}

			const displayEntity = String(this.config.display_entity || '');
			if (!displayEntity) {
				return null;
			}

			if (/^sensor\..+_timer_\d+_remaining$/.test(displayEntity)) {
				return displayEntity.replace(/_remaining$/, '_status');
			}
			if (/^sensor\..+_timer_\d+_remaining_friendly$/.test(displayEntity)) {
				return displayEntity.replace(/_remaining_friendly$/, '_status');
			}
			if (/^(text|input_text)\..+_timer_\d+_duration$/.test(displayEntity)) {
				return displayEntity.replace(/^(text|input_text)\./, 'sensor.').replace(/_duration$/, '_status');
			}

			return null;
		}

		_getResolvedInputBackground(status) {
			if (!this._hass || !this.config) {
				return this.config?.input_background ?? null;
			}
			if (this._isStatusColorTargetEnabled('input')) {
				const statusColor = this._getStatusColor(status);
				if (statusColor != null) {
					return statusColor;
				}
			}
			return this.config.input_background;
		}

		_getResolvedCardBackground(status) {
			if (!this._hass || !this.config) {
				return this.config?.card_background ?? null;
			}
			if (this._isStatusColorTargetEnabled('card')) {
				const statusColor = this._getStatusColor(status);
				if (statusColor != null) {
					return statusColor;
				}
			}
			return this.config.card_background;
		}

		_normalizeFlexPosition(value, axis) {
			const normalized = String(value || '').toLowerCase();
			if (normalized === 'left' || normalized === 'start' || normalized === 'flex-start') {
				return 'flex-start';
			}
			if (normalized === 'right' || normalized === 'end' || normalized === 'flex-end') {
				return 'flex-end';
			}
			if (normalized === 'top' && axis === 'vertical') {
				return 'flex-start';
			}
			if (normalized === 'bottom' && axis === 'vertical') {
				return 'flex-end';
			}
			if (normalized === 'middle') {
				return 'center';
			}
			if (normalized === 'stretch' && axis === 'vertical') {
				return 'stretch';
			}
			return 'center';
		}

		_getActiveSegments() {
			const segs = [];
			if (this.config.show_days) {
				segs.push({ key: 'days', prop: 'daysText', max: 99, placeholder: this.config.days_placeholder, unit: this.config.unit_suffix_days });
			}
			segs.push({ key: 'hours', prop: 'hourText', max: 23, placeholder: this.config.hour_placeholder, unit: this.config.unit_suffix_hours });
			segs.push({ key: 'minutes', prop: 'minuteText', max: 59, placeholder: this.config.minute_placeholder, unit: this.config.unit_suffix_minutes });
			if (this.config.show_seconds) {
				segs.push({ key: 'seconds', prop: 'secondText', max: 59, placeholder: this.config.second_placeholder, unit: this.config.unit_suffix_seconds });
			}
			return segs;
		}

		_getSuffixStyle() {
			return [
				this.config.suffix_font_size != null ? `font-size: ${this.config.suffix_font_size}` : '',
				this.config.suffix_color != null ? `color: ${this.config.suffix_color}` : '',
				this.config.suffix_padding != null ? `padding: ${this.config.suffix_padding}` : '',
				this.config.suffix_opacity != null ? `opacity: ${this.config.suffix_opacity}` : '',
			].filter(Boolean).join('; ');
		}

		render() {
			if (!this.stateObj) {
				return html`
					<ha-card .hass="${this._hass}" .config="${this.config}">
						<div class="wrapper">
							<span class="missing-entity">Missing entity: ${this.config?.display_entity || this.config?.entity || ''}</span>
						</div>
					</ha-card>
				`;
			}

			const interactive = !this.config.read_only;
			const currentStatus = this._getCurrentStatus();
			const resolvedInputBackground = this._getResolvedInputBackground(currentStatus);
			const resolvedCardBackground = this._getResolvedCardBackground(currentStatus);

			const cardStyle = [
				resolvedCardBackground != null ? `--ha-card-background: ${resolvedCardBackground}` : '',
				this.config.card_border === false ? '--ha-card-border-width: 0; --ha-card-box-shadow: none' : '',
				this.config.color != null ? `color: ${this.config.color}` : '',
				this.config.font_size != null ? `font-size: ${this.config.font_size}em` : '',
				this.config.content_justify != null ? `--stpc-justify-content: ${this.config.content_justify}` : '',
				this.config.content_align != null ? `--stpc-align-items: ${this.config.content_align}` : '',
				this.config.padding != null ? `padding: ${this.config.padding}` : '',
				this.config.padding_top_bottom != null ? `padding-top: ${this.config.padding_top_bottom}; padding-bottom: ${this.config.padding_top_bottom}` : '',
				this.config.padding_left_right != null ? `padding-left: ${this.config.padding_left_right}; padding-right: ${this.config.padding_left_right}` : '',
				this.config.input_width != null ? `--stpc-input-width: ${this.config.input_width}` : '',
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

			const suffixStyle = this._getSuffixStyle();

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
					<div class="wrapper">
						${this._getActiveSegments().map((seg, i) => html`
							${this.config.separator_mode === 'colon' && i > 0 ? html`<span class="separator" style="${suffixStyle}">${this.config.separator}</span>` : ''}
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
										@blur="${this._onCommit}"
										@keydown="${this._onKeydown}"
									/>
								</div>
								${this.config.show_steppers && interactive ? html`
									<button
										type="button"
										class="stepper-btn up"
										@pointerdown="${this._onStepperPointerDown}"
										@click="${() => this._stepSegment(seg.key, 1)}"
										aria-label="Increase ${seg.key}"
									>
										<span class="stepper-glyph"></span>
									</button>
									<button
										type="button"
										class="stepper-btn down"
										@pointerdown="${this._onStepperPointerDown}"
										@click="${() => this._stepSegment(seg.key, -1)}"
										aria-label="Decrease ${seg.key}"
									>
										<span class="stepper-glyph"></span>
									</button>
								` : ''}
							</div>
							${this.config.separator_mode === 'units' ? html`<span class="separator" style="${suffixStyle}">${seg.unit}</span>` : ''}
						`)}
					</div>
				</ha-card>
			`;
		}

		_onStepperPointerDown(ev) {
			if (this.config.read_only) {
				return;
			}
			ev.preventDefault();
		}

		_stepSegment(segKey, delta) {
			if (this.config.read_only) {
				return;
			}
			const seg = this._getActiveSegments().find((item) => item.key === segKey);
			if (!seg) {
				return;
			}
			const current = parseInt(this[seg.prop] || '0', 10);
			const currentNum = Number.isNaN(current) ? 0 : current;
			let next = currentNum + delta;
			if (this.config.stepper_wrap) {
				const span = seg.max + 1;
				next = ((next % span) + span) % span;
			} else {
				next = Math.max(0, Math.min(seg.max, next));
			}
			this[seg.prop] = String(next).padStart(2, '0');
			if (this.config.autosave) {
				this._save();
			}
		}

		_onInput(segKey, ev) {
			if (this.config.read_only) {
				return;
			}
			const prop = { days: 'daysText', hours: 'hourText', minutes: 'minuteText', seconds: 'secondText' }[segKey];
			const val = this._digitsOnly(ev.target.value);
			ev.target.value = val;
			this[prop] = val;
			const segs = this._getActiveSegments();
			if (this.config.autosave && segs.every(s => this[s.prop].length === 2)) {
				this._save();
			}
		}

		_onKeydown(ev) {
			if (this.config.read_only) {
				return;
			}
			if (ev.key !== 'Enter') {
				return;
			}
			ev.preventDefault();
			this._save();
			ev.target.blur();
		}

		_onCommit() {
			if (this.config.read_only) {
				return;
			}
			if (this.config.autosave) {
				this._save();
			}
		}

		_syncFromState() {
			// Don't overwrite what the user is currently typing
			if (this.shadowRoot && this.shadowRoot.activeElement) {
				return;
			}
			const raw = String(this.stateObj?.state || '');
			const now = Date.now();
			if (this._pendingValue) {
				if (raw === this._pendingValue) {
					this._pendingValue = null;
					this._pendingPrevValue = null;
					this._pendingSince = 0;
					this._pendingUntil = 0;
				} else {
					const isKnownStale = this._pendingPrevValue != null && raw === this._pendingPrevValue;
					const staleHoldUntil = this._pendingSince + (Number.isFinite(this.config.pending_stale_ms) ? this.config.pending_stale_ms : 3000);
					if (now < this._pendingUntil || (isKnownStale && now < staleHoldUntil)) {
						return;
					}
					this._pendingValue = null;
					this._pendingPrevValue = null;
					this._pendingSince = 0;
					this._pendingUntil = 0;
				}
			}
			const parts = raw.split(':');
			this._getActiveSegments().forEach((seg, i) => {
				this[seg.prop] = this._digitsOnly(parts[i] || '');
			});
		}

		_digitsOnly(val) {
			return String(val || '').replace(/\D/g, '').slice(0, 2);
		}

		_save() {
			if (this.config.read_only) {
				return;
			}
			if (!this._hass || !this.stateObj || !this.config.entity) {
				return;
			}
			const segs = this._getActiveSegments();
			if (segs.every(s => this[s.prop].length === 0)) {
				return;
			}
			const nums = segs.map(s => parseInt(this[s.prop] || '0', 10));
			if (nums.some(n => Number.isNaN(n))) {
				return;
			}
			if (segs.some((s, i) => nums[i] < 0 || nums[i] > s.max)) {
				return;
			}
			const value = nums.map(n => String(n).padStart(2, '0')).join(':');
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

	if (!customElements.get('snoozefest-time-picker-card')) {
		customElements.define('snoozefest-time-picker-card', SnoozefestTimePickerCard);
		console.info(
			`%c  snoozefest-time-picker-card \n%c  version: ${version}    `,
			'color: orange; font-weight: bold; background: black',
			'color: white; font-weight: bold; background: dimgray',
		);
	}
})(window.LitElement || Object.getPrototypeOf(customElements.get('hui-masonry-view') || customElements.get('hui-view')));
