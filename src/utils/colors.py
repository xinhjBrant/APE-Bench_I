# Copyright (2025) Bytedance Ltd. and/or its affiliates.

from copy import deepcopy
import random
import numpy as np

# Existing color palette
colors = dict(red_colors = [
    # "#672F2F", # dark blood red
    # "#E16A54", # bright red
    "#BE3144", # red
    "#810000", # dark red
],
green_colors = [
    # "#99B19C", # light green
    "#A9B388", # light grass green
    # "#3F4F44", # green
    "#5F6F52", # grass green
    # "#2C3930", # dark green
],
yellow_colors = [
    "#DDA853", # earth yellow
    # "#ECE5C7", # very light brown
    "#CDC2AE", # light brown
    "#A27B5C", # brown
],
blue_colors = [
    # "#C2DEDC", # light blue
    # "#116A7B", # lake blue
    "#27548A", # blue
    "#123458", # dark blue
]
)

def increase_grayscale(hex_color, amount=0.3):
    """
    Increase the grayscale of a hex color by reducing saturation
    
    Parameters:
    hex_color -- hex color string (e.g. "#672F2F")
    amount -- degree of grayscale increase (0.0 to 1.0)
    
    Returns:
    Hex color with increased grayscale
    """
    # Convert hex to RGB
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    
    # Reduce saturation (move towards average)
    avg = (r + g + b) // 3
    r = int(r * (1 - amount) + avg * amount)
    g = int(g * (1 - amount) + avg * amount)
    b = int(b * (1 - amount) + avg * amount)
    
    # Convert back to hex
    return f"#{r:02x}{g:02x}{b:02x}"

class ColorPicker:
    def __init__(self, color_palette=None, grayscale_increment=0.1):
        """
        Initialize the color picker
        
        Parameters:
        color_palette -- dictionary of color groups, defaults to module's colors
        grayscale_increment -- grayscale amount to increase when all colors are used
        """
        if color_palette is None:
            color_palette = colors
            
        self.original_palette = deepcopy(color_palette)  # Save original palette
        self.grayscale_increment = grayscale_increment
        self.current_palette = deepcopy(color_palette)   # Working palette
        self.grayscale_level = 0
        self.used_colors = set()  # Track all used colors
    
    def get_color(self):
        """
        Get a color according to rules:
        Pick a color from the group with fewest remaining colors, without replacement
        When all colors are picked, increase grayscale and reset the palette
        
        Returns:
        Selected color
        """
        # Check if all groups are empty
        while True:
            all_empty = True
            none_empty_list = []
            for colors_list in self.current_palette.values():
                if colors_list:
                    all_empty = False
                    none_empty_list.append(colors_list)
            
            # If all groups are empty, increase grayscale and reset palette
            if all_empty:
                self.grayscale_level += self.grayscale_increment
                self._reset_palette()
            else:
                break
        
        # Randomly select a group
        group = random.choice(none_empty_list)
        # Take middle color from selected group
        mu = (len(group) - 1) / 2
        sigma = len(group) / 4

        # Generate normal distribution index and constrain to list range
        idx = max(0, min(len(group) - 1, int(np.random.normal(mu, sigma))))
        selected_color = group.pop(idx)
        self.used_colors.add(selected_color)
        
        return selected_color
    
    def _reset_palette(self):
        """
        Reset current palette, increase grayscale for each color in original palette, ensure generated colors are unique
        """
        self.current_palette = {}
        
        for group, colors_list in self.original_palette.items():
            self.current_palette[group] = []
            for color in colors_list:
                # Calculate new color with base grayscale increase
                new_color = increase_grayscale(color, self.grayscale_level)
                
                # If this color has been used, adjust grayscale until a unique color is generated
                attempts = 0
                while new_color in self.used_colors and attempts < 10:
                    # Gradually increase grayscale to get a new color
                    adjustment = 0.05 + attempts * 0.02
                    new_color = increase_grayscale(color, self.grayscale_level + adjustment)
                    attempts += 1
                
                # If still can't find a unique color, generate a fine-tuned color
                if new_color in self.used_colors:
                    # Extract RGB from original color
                    base_color = new_color.lstrip('#')
                    r = int(base_color[0:2], 16)
                    g = int(base_color[2:4], 16)
                    b = int(base_color[4:6], 16)
                    
                    # Fine-tune RGB values, ensure within valid range
                    r = max(0, min(255, r + random.randint(-20, 20)))
                    g = max(0, min(255, g + random.randint(-20, 20)))
                    b = max(0, min(255, b + random.randint(-20, 20)))
                    
                    new_color = f"#{r:02x}{g:02x}{b:02x}"
                    
                    # Ensure final generated color is unique
                    while new_color in self.used_colors:
                        r = max(0, min(255, r + random.randint(-10, 10)))
                        g = max(0, min(255, g + random.randint(-10, 10)))
                        b = max(0, min(255, b + random.randint(-10, 10)))
                        new_color = f"#{r:02x}{g:02x}{b:02x}"
                
                self.current_palette[group].append(new_color)

# Usage example
if __name__ == "__main__":
    picker = ColorPicker()
    for i in range(20):
        color = picker.get_color()
        print(f"Color #{i+1}: {color}")