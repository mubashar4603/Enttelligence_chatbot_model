"""
Enhanced Query Handler for natural language movie queries
Handles analytical queries with GPT-like natural language responses
"""

import re
import logging
from typing import Dict, Any, List, Optional
from django.db.models import (
    Count, Sum, Avg, Max, Min, Q, F, 
    CharField, FloatField, ExpressionWrapper
)
from django.db.models.functions import ExtractHour, ExtractWeekDay
from movies.models import Movie

logger = logging.getLogger(__name__)


class EnhancedQueryHandler:
    """Enhanced handler for natural language movie queries"""
    
    def __init__(self, rag_service=None):
        """Initialize the enhanced query handler"""
        from chat.rag_service import get_rag_service
        self.rag_service = rag_service or get_rag_service()
        
        # Query type patterns
        self.query_patterns = {
            'count': [
                r'how many',
                r'total number',
                r'count',
                r'number of'
            ],
            'sum': [
                r'sum of',
                r'total (?:number of )?(seats|reserved|available)',
                r'add up',
                r'aggregate'
            ],
            'average': [
                r'average',
                r'avg',
                r'mean',
                r'typical'
            ],
            'top': [
                r'top \d+',
                r'best',
                r'highest',
                r'most popular',
                r'most expensive',
                r'cheapest'
            ],
            'list': [
                r'show me',
                r'list',
                r'what are',
                r'tell me about',
                r'find'
            ]
        }
        
        # Filter patterns
        self.filter_patterns = {
            'genre': r'(horror|action|comedy|drama|sci-?fi|thriller|romance|documentary|animation|adventure|fantasy|crime|mystery|western|war|musical|biography|history|family|sport)',
            'rating': r'(G|PG|PG-13|R|NC-17|NR|Not Rated)',
            'format': r'(IMAX|3D|2D|4DX|Standard|Dolby|DBOX)',
            'title': r'["\']([^"\']+)["\']',
            'city': r'in ([A-Za-z\s]+?)(?:\s+city)?(?:\s|,|and|$)',
            'state': r'(?:in|from)\s+(California|New York|Texas|Florida|Illinois|Pennsylvania|Ohio|Georgia|North Carolina|Michigan|Alabama|Alaska|Arizona|Arkansas|Colorado|Connecticut|Delaware|Hawaii|Idaho|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|North Dakota|Oklahoma|Oregon|Rhode Island|South Carolina|South Dakota|Tennessee|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|CA|NY|TX|FL|IL|PA|OH|GA|NC|MI)',
            'theater_chain': r'(AMC|Regal|Cinemark|Cineplex|Marcus|Alamo Drafthouse|iPic|ShowPlace|Harkins)',
            'theater': r'(?:at|in)\s+([A-Za-z\s]+?)\s+(?:theater|cinema)',
            'price_range': r'\$(\d+(?:\.\d{2})?)\s*(?:to|-)\s*\$(\d+(?:\.\d{2})?)',
            'price_under': r'(?:under|less than|below)\s*\$(\d+(?:\.\d{2})?)',
            'price_over': r'(?:over|more than|above)\s*\$(\d+(?:\.\d{2})?)',
        }
    
    def detect_query_type(self, query: str) -> str:
        """Detect the type of query"""
        query_lower = query.lower()
        
        # Check for specific query types
        for query_type, patterns in self.query_patterns.items():
            if any(re.search(pattern, query_lower) for pattern in patterns):
                return query_type
        
        # Default to list/search
        return 'list'
    
    def extract_filters(self, query: str) -> Dict[str, Any]:
        """Extract filters from the query"""
        filters = {}
        query_lower = query.lower()
        
        # Extract genre
        genre_match = re.search(self.filter_patterns['genre'], query_lower, re.IGNORECASE)
        if genre_match:
            filters['genre'] = genre_match.group(1)
        
        # Extract rating
        rating_match = re.search(self.filter_patterns['rating'], query, re.IGNORECASE)
        if rating_match:
            filters['rating'] = rating_match.group(1)
        
        # Extract format
        format_match = re.search(self.filter_patterns['format'], query_lower, re.IGNORECASE)
        if format_match:
            filters['format'] = format_match.group(1)
        
        # Extract title
        title_match = re.search(self.filter_patterns['title'], query, re.IGNORECASE)
        if title_match:
            filters['title'] = title_match.group(1)
        
        # Extract city
        city_match = re.search(self.filter_patterns['city'], query, re.IGNORECASE)
        if city_match:
            filters['city'] = city_match.group(1).strip()
        
        # Extract state
        state_match = re.search(self.filter_patterns['state'], query, re.IGNORECASE)
        if state_match:
            state_name = state_match.group(1)
            # Convert full state name to abbreviation if needed
            state_abbrev_map = {
                'California': 'CA', 'New York': 'NY', 'Texas': 'TX', 
                'Florida': 'FL', 'Illinois': 'IL', 'Pennsylvania': 'PA'
            }
            filters['state'] = state_abbrev_map.get(state_name, state_name)
        
        # Extract theater chain
        chain_match = re.search(self.filter_patterns['theater_chain'], query, re.IGNORECASE)
        if chain_match:
            filters['theater_chain'] = chain_match.group(1)
        
        # Extract price range
        price_match = re.search(self.filter_patterns['price_range'], query)
        if price_match:
            filters['price_min'] = float(price_match.group(1))
            filters['price_max'] = float(price_match.group(2))
        
        # Extract price under
        price_under_match = re.search(self.filter_patterns['price_under'], query)
        if price_under_match:
            filters['price_max'] = float(price_under_match.group(1))
        
        # Extract price over
        price_over_match = re.search(self.filter_patterns['price_over'], query)
        if price_over_match:
            filters['price_min'] = float(price_over_match.group(1))
        
        return filters
    
    def apply_filters(self, queryset, filters: Dict[str, Any]):
        """Apply filters to the queryset"""
        if 'genre' in filters:
            queryset = queryset.filter(genre__iexact=filters['genre'])
        
        if 'rating' in filters:
            queryset = queryset.filter(rating__iexact=filters['rating'])
        
        if 'format' in filters:
            queryset = queryset.filter(
                Q(screen_format__icontains=filters['format']) |
                Q(movie_format__icontains=filters['format'])
            )
        
        if 'title' in filters:
            queryset = queryset.filter(title__icontains=filters['title'])
        
        if 'city' in filters:
            queryset = queryset.filter(theater_city__iexact=filters['city'])
        
        if 'state' in filters:
            queryset = queryset.filter(theater_state__iexact=filters['state'])
        
        if 'theater_chain' in filters:
            queryset = queryset.filter(circuit_name__icontains=filters['theater_chain'])
        
        if 'price_min' in filters:
            queryset = queryset.filter(price__gte=filters['price_min'])
        
        if 'price_max' in filters:
            queryset = queryset.filter(price__lte=filters['price_max'])
        
        return queryset
    
    def handle_count_query(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle count queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Get unique count (by title or all records)
            if 'title' in query.lower() and 'showtime' not in query.lower():
                count = queryset.values('title').distinct().count()
                item_type = "unique movies"
            else:
                count = queryset.count()
                item_type = "showtimes"
            
            # Generate natural language response
            filter_desc = self._generate_filter_description(filters)
            
            message = f"I found **{count:,} {item_type}**"
            if filter_desc:
                message += f" {filter_desc}"
            message += "."
            
            if count > 0 and count < 10:
                # Add some examples
                examples = queryset.values('title').distinct()[:5]
                if examples:
                    titles = [ex['title'] for ex in examples]
                    message += f"\n\nSome examples: {', '.join(titles)}."
            
            return {
                'type': 'analytical',
                'message': message,
                'data': {
                    'count': count,
                    'filters': filters,
                    'item_type': item_type
                }
            }
            
        except Exception as e:
            logger.error(f"Error in count query: {e}")
            return self._error_response(str(e))
    
    def handle_sum_query(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sum/aggregation queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Determine what to sum
            field_to_sum = None
            field_name = None
            
            if 'reserved' in query.lower():
                field_to_sum = 'reserved'
                field_name = 'reserved seats'
            elif 'available' in query.lower():
                field_to_sum = 'available'
                field_name = 'available seats'
            elif 'total seats' in query.lower() or 'capacity' in query.lower():
                field_to_sum = 'total_seats'
                field_name = 'total seats'
            elif 'price' in query.lower() or 'revenue' in query.lower():
                field_to_sum = 'price'
                field_name = 'ticket revenue'
            
            if not field_to_sum:
                return self._error_response("I couldn't determine what you want to sum. Please specify (e.g., reserved seats, available seats, total seats).")
            
            result = queryset.aggregate(
                total=Sum(field_to_sum),
                avg=Avg(field_to_sum),
                count=Count('id')
            )
            
            total = result['total'] or 0
            avg = result['avg'] or 0
            count = result['count']
            
            filter_desc = self._generate_filter_description(filters)
            
            if field_to_sum == 'price':
                message = f"Based on {count:,} showtimes{filter_desc}, the total {field_name} would be **${total:,.2f}** (average: ${avg:.2f} per ticket)."
            else:
                message = f"Based on {count:,} showtimes{filter_desc}, the total {field_name} is **{total:,}** (average: {avg:.0f} per showtime)."
            
            return {
                'type': 'analytical',
                'message': message,
                'data': {
                    'total': float(total),
                    'average': float(avg),
                    'count': count,
                    'field': field_name,
                    'filters': filters
                }
            }
            
        except Exception as e:
            logger.error(f"Error in sum query: {e}")
            return self._error_response(str(e))
    
    def handle_average_query(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle average queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Determine what to average
            metrics = {}
            
            if 'price' in query.lower():
                metrics['price'] = ('price', 'ticket price', '$')
            if 'occupancy' in query.lower() or 'filled' in query.lower():
                # Calculate occupancy rate
                pass
            if 'seats' in query.lower() or 'capacity' in query.lower():
                metrics['seats'] = ('total_seats', 'theater capacity', '')
            if 'reserved' in query.lower():
                metrics['reserved'] = ('reserved', 'reserved seats', '')
            
            if not metrics:
                metrics['price'] = ('price', 'ticket price', '$')
            
            results = {}
            for key, (field, label, prefix) in metrics.items():
                agg = queryset.aggregate(
                    avg=Avg(field),
                    min=Min(field),
                    max=Max(field),
                    count=Count('id')
                )
                results[key] = {
                    'label': label,
                    'prefix': prefix,
                    'avg': agg['avg'] or 0,
                    'min': agg['min'] or 0,
                    'max': agg['max'] or 0,
                    'count': agg['count']
                }
            
            filter_desc = self._generate_filter_description(filters)
            count = list(results.values())[0]['count'] if results else 0
            
            message = f"Based on **{count:,} showtimes**{filter_desc}:\n\n"
            
            for key, data in results.items():
                prefix = data['prefix']
                message += f"**{data['label'].title()}:**\n"
                message += f"  • Average: {prefix}{data['avg']:.2f}\n"
                message += f"  • Range: {prefix}{data['min']:.2f} - {prefix}{data['max']:.2f}\n\n"
            
            return {
                'type': 'analytical',
                'message': message.strip(),
                'data': {
                    'metrics': results,
                    'filters': filters
                }
            }
            
        except Exception as e:
            logger.error(f"Error in average query: {e}")
            return self._error_response(str(e))
    
    def handle_top_query(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle top N queries"""
        try:
            # Extract limit
            limit_match = re.search(r'top (\d+)', query.lower())
            limit = int(limit_match.group(1)) if limit_match else 10
            limit = min(limit, 50)  # Cap at 50
            
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Determine sorting criteria
            order_by = None
            metric_name = None
            ascending = False
            
            if 'expensive' in query.lower() or 'highest price' in query.lower():
                order_by = '-price'
                metric_name = 'most expensive'
            elif 'cheap' in query.lower() or 'lowest price' in query.lower():
                order_by = 'price'
                metric_name = 'cheapest'
                ascending = True
            elif 'popular' in query.lower() or 'full' in query.lower() or 'occupied' in query.lower():
                order_by = '-reserved'
                metric_name = 'most popular (by reservations)'
            elif 'available' in query.lower() or 'empty' in query.lower():
                order_by = 'reserved'
                metric_name = 'most available'
                ascending = True
            elif 'rated' in query.lower() or 'rating' in query.lower():
                # Group by title and show unique movies
                movies = queryset.values('title', 'genre', 'rating').annotate(
                    showtime_count=Count('id'),
                    avg_price=Avg('price')
                ).order_by('-showtime_count')[:limit]
                
                filter_desc = self._generate_filter_description(filters)
                message = f"Here are the **top {len(movies)} movies** by number of showtimes{filter_desc}:\n\n"
                
                for i, movie in enumerate(movies, 1):
                    message += f"{i}. **{movie['title']}** ({movie['rating']})\n"
                    message += f"   • Genre: {movie['genre']}\n"
                    message += f"   • {movie['showtime_count']} showtimes, avg price: ${movie['avg_price']:.2f}\n\n"
                
                return {
                    'type': 'analytical',
                    'message': message.strip(),
                    'data': {
                        'movies': list(movies),
                        'limit': limit,
                        'filters': filters
                    }
                }
            else:
                # Default: most showtimes
                order_by = '-id'
                metric_name = 'latest'
            
            if not order_by:
                order_by = '-price'
                metric_name = 'most expensive'
            
            results = queryset.order_by(order_by)[:limit]
            
            filter_desc = self._generate_filter_description(filters)
            message = f"Here are the **top {len(results)} {metric_name} showtimes**{filter_desc}:\n\n"
            
            for i, movie in enumerate(results, 1):
                message += f"{i}. **{movie.title}** at {movie.theater_name}\n"
                message += f"   • {movie.date_sh.strftime('%b %d, %Y')} at {movie.time_sh.strftime('%I:%M %p')}\n"
                message += f"   • Price: ${movie.price:.2f} | Format: {movie.screen_format}\n"
                message += f"   • Seats: {movie.reserved}/{movie.total_seats} reserved\n\n"
            
            return {
                'type': 'analytical',
                'message': message.strip(),
                'data': {
                    'results': [
                        {
                            'title': m.title,
                            'theater': m.theater_name,
                            'date': str(m.date_sh),
                            'time': str(m.time_sh),
                            'price': float(m.price),
                            'format': m.screen_format,
                            'reserved': m.reserved,
                            'total_seats': m.total_seats
                        } for m in results
                    ],
                    'limit': limit,
                    'filters': filters
                }
            }
            
        except Exception as e:
            logger.error(f"Error in top query: {e}")
            return self._error_response(str(e))
    
    def handle_list_query(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list/show queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Get unique movies or showtimes
            if 'movie' in query.lower() and 'showtime' not in query.lower():
                # List unique movies
                movies = queryset.values('title', 'genre', 'rating').annotate(
                    showtime_count=Count('id'),
                    avg_price=Avg('price'),
                    total_reserved=Sum('reserved')
                ).order_by('-showtime_count')[:20]
                
                count = len(movies)
                total_count = queryset.values('title').distinct().count()
                
                filter_desc = self._generate_filter_description(filters)
                message = f"I found **{total_count} unique movies**{filter_desc}. Here are the top {count}:\n\n"
                
                for i, movie in enumerate(movies, 1):
                    message += f"{i}. **{movie['title']}** ({movie['rating']})\n"
                    message += f"   • Genre: {movie['genre']}\n"
                    message += f"   • {movie['showtime_count']} showtimes, avg ${movie['avg_price']:.2f}\n"
                    message += f"   • Total seats reserved: {movie['total_reserved']:,}\n\n"
                
                return {
                    'type': 'analytical',
                    'message': message.strip(),
                    'data': {
                        'movies': list(movies),
                        'total_count': total_count,
                        'filters': filters
                    }
                }
            else:
                # List showtimes
                showtimes = queryset.select_related()[:15]
                count = queryset.count()
                
                filter_desc = self._generate_filter_description(filters)
                message = f"I found **{count:,} showtimes**{filter_desc}. Here are the first 15:\n\n"
                
                for i, show in enumerate(showtimes, 1):
                    message += f"{i}. **{show.title}** at {show.theater_name}\n"
                    message += f"   • {show.date_sh.strftime('%b %d, %Y')} at {show.time_sh.strftime('%I:%M %p')}\n"
                    message += f"   • ${show.price:.2f} | {show.screen_format} | {show.genre}\n"
                    message += f"   • {show.reserved}/{show.total_seats} seats reserved\n\n"
                
                if count > 15:
                    message += f"\n_...and {count - 15:,} more showtimes._"
                
                return {
                    'type': 'analytical',
                    'message': message.strip(),
                    'data': {
                        'count': count,
                        'filters': filters
                    }
                }
            
        except Exception as e:
            logger.error(f"Error in list query: {e}")
            return self._error_response(str(e))
    
    def _generate_filter_description(self, filters: Dict[str, Any]) -> str:
        """Generate natural language description of filters"""
        if not filters:
            return ""
        
        parts = []
        
        if 'genre' in filters:
            parts.append(f"{filters['genre']} genre")
        if 'rating' in filters:
            parts.append(f"rated {filters['rating']}")
        if 'format' in filters:
            parts.append(f"in {filters['format']} format")
        if 'title' in filters:
            parts.append(f"for '{filters['title']}'")
        if 'theater_chain' in filters:
            parts.append(f"at {filters['theater_chain']} theaters")
        if 'city' in filters:
            parts.append(f"in {filters['city']}")
        if 'state' in filters:
            parts.append(f"in {filters['state']}")
        if 'price_min' in filters and 'price_max' in filters:
            parts.append(f"priced ${filters['price_min']:.2f}-${filters['price_max']:.2f}")
        elif 'price_max' in filters:
            parts.append(f"under ${filters['price_max']:.2f}")
        elif 'price_min' in filters:
            parts.append(f"over ${filters['price_min']:.2f}")
        
        if not parts:
            return ""
        
        return " " + ", ".join(parts)
    
    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Generate error response"""
        return {
            'type': 'error',
            'error': error_msg,
            'message': f"I encountered an issue: {error_msg}\n\nPlease try rephrasing your query or ask me about:\n• Total number of movies by genre\n• Top rated movies\n• Sum of reserved seats\n• Average prices\n• Movies in specific cities"
        }
    
    def handle_theater_analysis(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle complex theater analysis queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            # Extract theater name if specified
            theater_pattern = r'(?:at|in|for)\s+([A-Za-z\s]+?)\s+theater'
            theater_match = re.search(theater_pattern, query, re.IGNORECASE)
            if theater_match:
                theater_name = theater_match.group(1).strip()
                queryset = queryset.filter(theater_name__icontains=theater_name)
                filters['theater'] = theater_name
            
            # Get theater statistics
            theater_stats = queryset.values('theater_name', 'theater_city', 'theater_state').annotate(
                total_screens=Count('auditorium', distinct=True),
                total_showtimes=Count('id'),
                avg_capacity=Avg('total_seats'),
                avg_price=Avg('price'),
                total_reserved=Sum('reserved'),
                total_seats=Sum('total_seats'),
                premium_screens=Count('screen_format', filter=Q(
                    screen_format__in=['IMAX', '3D', '4DX', 'Dolby', 'DBOX']
                ))
            ).annotate(
                occupancy_rate=ExpressionWrapper(
                    F('total_reserved') * 100.0 / F('total_seats'),
                    output_field=FloatField()
                ),
                premium_percentage=ExpressionWrapper(
                    F('premium_screens') * 100.0 / F('total_screens'),
                    output_field=FloatField()
                )
            ).order_by('-total_showtimes')
            
            if not theater_stats:
                return self._error_response("No theater data found matching your criteria.")
            
            filter_desc = self._generate_filter_description(filters)
            message = f"# Theater Analysis{filter_desc}\n\n"
            
            for i, theater in enumerate(theater_stats[:10], 1):
                message += f"## {i}. {theater['theater_name']}\n"
                message += f"**Location:** {theater['theater_city']}, {theater['theater_state']}\n\n"
                message += f"📊 **Statistics:**\n"
                message += f"  • Total screens: **{theater['total_screens']}**\n"
                message += f"  • Average seat capacity: **{theater['avg_capacity']:.0f}** seats\n"
                message += f"  • Premium format screens: **{theater['premium_percentage']:.1f}%**\n"
                message += f"  • Average ticket price: **${theater['avg_price']:.2f}**\n"
                message += f"  • Total reserved seats: **{theater['total_reserved']:,}**\n"
                message += f"  • Occupancy rate: **{theater['occupancy_rate']:.1f}%**\n"
                message += f"  • Total showtimes: **{theater['total_showtimes']:,}**\n\n"
            
            return {
                'type': 'analytical',
                'message': message.strip(),
                'data': {
                    'theaters': list(theater_stats),
                    'filters': filters
                }
            }
            
        except Exception as e:
            logger.error(f"Error in theater analysis: {e}")
            return self._error_response(str(e))
    
    def handle_movie_breakdown(self, query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle detailed movie breakdown queries"""
        try:
            queryset = Movie.objects.all()
            queryset = self.apply_filters(queryset, filters)
            
            if not queryset.exists():
                return self._error_response(f"No data found for the specified movie.")
            
            # Get movie statistics
            total_showings = queryset.count()
            
            # Format breakdown
            format_stats = queryset.values('screen_format').annotate(
                count=Count('id'),
                avg_price=Avg('price'),
                avg_reserved=Avg('reserved'),
                total_reserved=Sum('reserved')
            ).order_by('-count')
            
            # Theater breakdown
            theater_stats = queryset.values('theater_name', 'theater_city').annotate(
                showings=Count('id'),
                total_reserved=Sum('reserved'),
                total_capacity=Sum('total_seats'),
                avg_price=Avg('price')
            ).annotate(
                attendance_rate=ExpressionWrapper(
                    F('total_reserved') * 100.0 / F('total_capacity'),
                    output_field=FloatField()
                )
            ).order_by('-attendance_rate')
            
            # Overall stats
            overall_stats = queryset.aggregate(
                avg_reserved=Avg('reserved'),
                total_reserved=Sum('reserved'),
                avg_price=Avg('price'),
                min_price=Min('price'),
                max_price=Max('price')
            )
            
            # Build response
            movie_title = filters.get('title', 'the specified movie')
            message = f"# Statistical Breakdown for '{movie_title}'\n\n"
            
            message += f"## 📊 Overall Statistics\n"
            message += f"  • Total number of showings: **{total_showings:,}**\n"
            message += f"  • Average seats reserved per showing: **{overall_stats['avg_reserved']:.0f}**\n"
            message += f"  • Total seats reserved: **{overall_stats['total_reserved']:,}**\n"
            message += f"  • Average ticket price: **${overall_stats['avg_price']:.2f}**\n"
            message += f"  • Price range: **${overall_stats['min_price']:.2f} - ${overall_stats['max_price']:.2f}**\n\n"
            
            message += f"## 🎬 Screening Formats\n"
            for fmt in format_stats:
                message += f"**{fmt['screen_format']}:**\n"
                message += f"  • Showings: {fmt['count']:,} ({fmt['count']/total_showings*100:.1f}%)\n"
                message += f"  • Avg price: ${fmt['avg_price']:.2f}\n"
                message += f"  • Avg reserved: {fmt['avg_reserved']:.0f} seats\n\n"
            
            message += f"## 🏛️ Top 5 Theaters by Attendance Rate\n"
            for i, theater in enumerate(theater_stats[:5], 1):
                message += f"{i}. **{theater['theater_name']}** ({theater['theater_city']})\n"
                message += f"   • Attendance rate: **{theater['attendance_rate']:.1f}%**\n"
                message += f"   • Showings: {theater['showings']}\n"
                message += f"   • Avg price: ${theater['avg_price']:.2f}\n\n"
            
            return {
                'type': 'analytical',
                'message': message.strip(),
                'data': {
                    'overall': overall_stats,
                    'formats': list(format_stats),
                    'theaters': list(theater_stats),
                    'total_showings': total_showings
                }
            }
            
        except Exception as e:
            logger.error(f"Error in movie breakdown: {e}")
            return self._error_response(str(e))
    
    def is_analytical_query(self, query: str) -> bool:
        """Determine if query is analytical or conversational"""
        analytical_keywords = [
            'how many', 'total', 'count', 'sum', 'average', 'avg',
            'top', 'best', 'highest', 'lowest', 'most', 'least',
            'list', 'show me', 'find', 'search', 'tell me the',
            'analyze', 'breakdown', 'statistics', 'compare', 'comparison'
        ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in analytical_keywords)
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Main entry point for processing queries"""
        try:
            if not query or not query.strip():
                return self._error_response("Please provide a question.")
            
            query_lower = query.lower()
            
            # Check if it's analytical or conversational
            if self.is_analytical_query(query):
                filters = self.extract_filters(query)
                
                # Check for complex analysis queries
                if 'analyze' in query_lower and 'theater' in query_lower:
                    return self.handle_theater_analysis(query, filters)
                
                if ('breakdown' in query_lower or 'statistical' in query_lower) and filters.get('title'):
                    return self.handle_movie_breakdown(query, filters)
                
                # Handle standard analytical queries
                query_type = self.detect_query_type(query)
                
                if query_type == 'count':
                    return self.handle_count_query(query, filters)
                elif query_type == 'sum':
                    return self.handle_sum_query(query, filters)
                elif query_type == 'average':
                    return self.handle_average_query(query, filters)
                elif query_type == 'top':
                    return self.handle_top_query(query, filters)
                elif query_type == 'list':
                    return self.handle_list_query(query, filters)
                else:
                    # Default to list
                    return self.handle_list_query(query, filters)
            else:
                # Use RAG for conversational queries
                try:
                    rag_response = self.rag_service.query(query)
                    if rag_response and rag_response.get('answer'):
                        return {
                            'type': 'rag',
                            'message': rag_response['answer'],
                            'sources': rag_response.get('sources', [])
                        }
                except Exception as e:
                    logger.error(f"RAG query failed: {e}")
                
                return self._error_response("I couldn't process that query. Please try asking about movie statistics, counts, or specific information.")
        
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return self._error_response(str(e))

