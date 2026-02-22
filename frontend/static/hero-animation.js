/**
 * CommonTrace Hero Animation
 *
 * Interactive neural network / knowledge graph canvas animation.
 * Adapted for LIGHT background — warm blues and teals on white/cream.
 * 250+ particles with connections, mouse interaction, accent colors.
 * Performance-optimized with requestAnimationFrame, throttled mouse events,
 * and device pixel ratio awareness.
 */
(function() {
  'use strict';

  // ---- Configuration ----
  var CONFIG = {
    particleCount: 280,
    particleCountMobile: 120,
    connectionDistance: 120,
    connectionDistanceMobile: 90,
    mouseRadius: 180,
    mouseRadiusMobile: 120,
    baseSpeed: 0.25,
    mouseInfluence: 0.012,
    particleMinSize: 1,
    particleMaxSize: 2.5,
    particleMinSizeMobile: 0.8,
    particleMaxSizeMobile: 2,
    connectionOpacity: 0.08,
    connectionMouseOpacity: 0.2,
    fps: 60,
    colors: [
      { r: 51, g: 102, b: 204 },   // Wikipedia blue
      { r: 100, g: 149, b: 237 },  // Cornflower blue
      { r: 70, g: 130, b: 180 },   // Steel blue
      { r: 72, g: 166, b: 167 },   // Teal
      { r: 147, g: 197, b: 253 },  // Light blue
      { r: 121, g: 92, b: 178 }    // Muted purple (visited link color)
    ]
  };

  // ---- Utility ----
  function isMobile() {
    return window.innerWidth < 768;
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  // ---- Particle class ----
  function Particle(width, height, config) {
    this.reset(width, height, config);
  }

  Particle.prototype.reset = function(width, height, config) {
    this.x = Math.random() * width;
    this.y = Math.random() * height;
    this.vx = (Math.random() - 0.5) * config.baseSpeed * 2;
    this.vy = (Math.random() - 0.5) * config.baseSpeed * 2;
    var colorIndex = Math.floor(Math.random() * config.colors.length);
    this.color = config.colors[colorIndex];
    var mobile = isMobile();
    var minSize = mobile ? config.particleMinSizeMobile : config.particleMinSize;
    var maxSize = mobile ? config.particleMaxSizeMobile : config.particleMaxSize;
    this.baseSize = minSize + Math.random() * (maxSize - minSize);
    this.size = this.baseSize;
    this.baseAlpha = 0.2 + Math.random() * 0.35;
    this.alpha = this.baseAlpha;
    this.pulsePhase = Math.random() * Math.PI * 2;
    this.pulseSpeed = 0.005 + Math.random() * 0.01;
  };

  Particle.prototype.update = function(width, height, mouseX, mouseY, mouseActive, config, time) {
    // Gentle floating motion with sine wave
    this.x += this.vx + Math.sin(time * 0.001 + this.pulsePhase) * 0.05;
    this.y += this.vy + Math.cos(time * 0.001 + this.pulsePhase * 1.3) * 0.05;

    // Wrap around edges with padding
    var pad = 20;
    if (this.x < -pad) this.x = width + pad;
    if (this.x > width + pad) this.x = -pad;
    if (this.y < -pad) this.y = height + pad;
    if (this.y > height + pad) this.y = -pad;

    // Mouse interaction
    var mouseRadius = isMobile() ? config.mouseRadiusMobile : config.mouseRadius;
    if (mouseActive) {
      var dx = this.x - mouseX;
      var dy = this.y - mouseY;
      var distSq = dx * dx + dy * dy;
      var radiusSq = mouseRadius * mouseRadius;

      if (distSq < radiusSq) {
        var dist = Math.sqrt(distSq);
        var force = (1 - dist / mouseRadius) * config.mouseInfluence;
        // Gentle push away from cursor
        this.vx += dx * force;
        this.vy += dy * force;
        // Brighten near mouse
        this.alpha = lerp(this.baseAlpha, 0.8, 1 - dist / mouseRadius);
        this.size = lerp(this.baseSize, this.baseSize * 2, (1 - dist / mouseRadius) * 0.5);
      } else {
        this.alpha = this.baseAlpha;
        this.size = this.baseSize;
      }
    } else {
      this.alpha = this.baseAlpha;
      this.size = this.baseSize;
    }

    // Gentle pulse
    this.alpha += Math.sin(time * this.pulseSpeed + this.pulsePhase) * 0.06;
    this.alpha = Math.max(0.08, Math.min(0.7, this.alpha));

    // Damping to keep velocities in check
    this.vx *= 0.998;
    this.vy *= 0.998;

    // Speed limit
    var speed = Math.sqrt(this.vx * this.vx + this.vy * this.vy);
    var maxSpeed = config.baseSpeed * 3;
    if (speed > maxSpeed) {
      this.vx = (this.vx / speed) * maxSpeed;
      this.vy = (this.vy / speed) * maxSpeed;
    }
  };

  // ---- Main Animation Controller ----
  function HeroAnimation(canvas) {
    if (!canvas || !canvas.getContext) return;

    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.mouseX = -1000;
    this.mouseY = -1000;
    this.mouseActive = false;
    this.running = true;
    this.lastFrame = 0;
    this.frameInterval = 1000 / CONFIG.fps;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);

    this.resize();
    this.initParticles();
    this.bindEvents();
    this.animate(0);
  }

  HeroAnimation.prototype.resize = function() {
    var rect = this.canvas.parentElement.getBoundingClientRect();
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.canvas.style.width = this.width + 'px';
    this.canvas.style.height = this.height + 'px';
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  };

  HeroAnimation.prototype.initParticles = function() {
    var count = isMobile() ? CONFIG.particleCountMobile : CONFIG.particleCount;
    this.particles = [];
    for (var i = 0; i < count; i++) {
      this.particles.push(new Particle(this.width, this.height, CONFIG));
    }
  };

  HeroAnimation.prototype.bindEvents = function() {
    var self = this;

    // Throttled mouse move
    var mouseThrottle = null;
    var heroSection = this.canvas.parentElement;

    document.addEventListener('mousemove', function(e) {
      if (mouseThrottle) return;
      mouseThrottle = requestAnimationFrame(function() {
        var rect = heroSection.getBoundingClientRect();
        self.mouseX = e.clientX - rect.left;
        self.mouseY = e.clientY - rect.top;
        self.mouseActive = (
          self.mouseX >= 0 && self.mouseX <= self.width &&
          self.mouseY >= 0 && self.mouseY <= self.height
        );
        mouseThrottle = null;
      });
    }, { passive: true });

    document.addEventListener('mouseleave', function() {
      self.mouseActive = false;
    }, { passive: true });

    // Touch support
    heroSection.addEventListener('touchmove', function(e) {
      if (mouseThrottle) return;
      mouseThrottle = requestAnimationFrame(function() {
        var touch = e.touches[0];
        if (touch) {
          var rect = heroSection.getBoundingClientRect();
          self.mouseX = touch.clientX - rect.left;
          self.mouseY = touch.clientY - rect.top;
          self.mouseActive = true;
        }
        mouseThrottle = null;
      });
    }, { passive: true });

    heroSection.addEventListener('touchend', function() {
      self.mouseActive = false;
    }, { passive: true });

    // Resize handler (debounced)
    var resizeTimer;
    window.addEventListener('resize', function() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function() {
        self.dpr = Math.min(window.devicePixelRatio || 1, 2);
        self.resize();
        // Reinitialize particles if count changed
        var newCount = isMobile() ? CONFIG.particleCountMobile : CONFIG.particleCount;
        if (self.particles.length !== newCount) {
          self.initParticles();
        }
      }, 200);
    }, { passive: true });

    // Visibility change: pause when hidden
    document.addEventListener('visibilitychange', function() {
      self.running = !document.hidden;
      if (self.running) {
        self.lastFrame = 0;
        requestAnimationFrame(function(t) { self.animate(t); });
      }
    });
  };

  HeroAnimation.prototype.drawConnections = function(time) {
    var particles = this.particles;
    var len = particles.length;
    var connDist = isMobile() ? CONFIG.connectionDistanceMobile : CONFIG.connectionDistance;
    var connDistSq = connDist * connDist;
    var mouseRadius = isMobile() ? CONFIG.mouseRadiusMobile : CONFIG.mouseRadius;
    var mouseRadiusSq = mouseRadius * mouseRadius;
    var ctx = this.ctx;
    var mouseX = this.mouseX;
    var mouseY = this.mouseY;
    var mouseActive = this.mouseActive;

    ctx.lineWidth = 0.5;

    for (var i = 0; i < len; i++) {
      var pi = particles[i];
      for (var j = i + 1; j < len; j++) {
        var pj = particles[j];
        var dx = pi.x - pj.x;
        var dy = pi.y - pj.y;
        var distSq = dx * dx + dy * dy;

        if (distSq < connDistSq) {
          var dist = Math.sqrt(distSq);
          var alpha = (1 - dist / connDist) * CONFIG.connectionOpacity;

          // Boost connections near mouse
          if (mouseActive) {
            var midX = (pi.x + pj.x) * 0.5;
            var midY = (pi.y + pj.y) * 0.5;
            var mDx = midX - mouseX;
            var mDy = midY - mouseY;
            var mDistSq = mDx * mDx + mDy * mDy;
            if (mDistSq < mouseRadiusSq) {
              var mDist = Math.sqrt(mDistSq);
              alpha = lerp(alpha, CONFIG.connectionMouseOpacity, 1 - mDist / mouseRadius);
            }
          }

          // Color: blend between the two particle colors
          var r = Math.round((pi.color.r + pj.color.r) * 0.5);
          var g = Math.round((pi.color.g + pj.color.g) * 0.5);
          var b = Math.round((pi.color.b + pj.color.b) * 0.5);

          ctx.beginPath();
          ctx.moveTo(pi.x, pi.y);
          ctx.lineTo(pj.x, pj.y);
          ctx.strokeStyle = 'rgba(' + r + ',' + g + ',' + b + ',' + alpha.toFixed(3) + ')';
          ctx.stroke();
        }
      }
    }
  };

  HeroAnimation.prototype.drawParticles = function(time) {
    var particles = this.particles;
    var len = particles.length;
    var ctx = this.ctx;

    for (var i = 0; i < len; i++) {
      var p = particles[i];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',' + p.alpha.toFixed(3) + ')';
      ctx.fill();

      // Draw subtle glow for brighter particles
      if (p.alpha > 0.45) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',' + (p.alpha * 0.04).toFixed(3) + ')';
        ctx.fill();
      }
    }
  };

  HeroAnimation.prototype.animate = function(timestamp) {
    if (!this.running) return;

    var self = this;
    requestAnimationFrame(function(t) { self.animate(t); });

    // Frame rate limiting
    if (timestamp - this.lastFrame < this.frameInterval) return;
    this.lastFrame = timestamp;

    var ctx = this.ctx;
    var width = this.width;
    var height = this.height;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Update particles
    var particles = this.particles;
    var len = particles.length;
    for (var i = 0; i < len; i++) {
      particles[i].update(width, height, this.mouseX, this.mouseY, this.mouseActive, CONFIG, timestamp);
    }

    // Draw connections then particles (particles on top)
    this.drawConnections(timestamp);
    this.drawParticles(timestamp);
  };

  HeroAnimation.prototype.destroy = function() {
    this.running = false;
  };

  // Expose as global
  window.HeroAnimation = HeroAnimation;

  // Reduced motion: skip canvas entirely
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.HeroAnimation = function() {};
  }

})();
